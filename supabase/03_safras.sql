-- Execute depois dos scripts 01 e 02. A safra é um nome, não uma regra de datas.
begin;
create table if not exists public.safras (
  id bigint generated always as identity primary key,
  usuario_id uuid not null default auth.uid() references auth.users(id),
  nome text not null check (length(btrim(nome)) between 1 and 100),
  padrao boolean not null default false,
  unique (usuario_id, nome),
  unique (id, usuario_id)
);
create unique index if not exists safras_uma_padrao_por_usuario on public.safras(usuario_id) where padrao;
alter table public.safras enable row level security;
drop policy if exists safras_do_usuario on public.safras;
create policy safras_do_usuario on public.safras for all to authenticated
  using (usuario_id = auth.uid()) with check (usuario_id = auth.uid());
grant select, insert, update, delete on public.safras to authenticated;
grant usage, select on sequence public.safras_id_seq to authenticated;

-- Preserva as PTVs existentes, associando-as à safra 2026 de seu proprietário.
insert into public.safras (usuario_id, nome, padrao)
select id, '2026', true from auth.users u
where not exists (select 1 from public.safras s where s.usuario_id = u.id and s.padrao)
on conflict (usuario_id, nome) do update set padrao = true;
alter table public.ptvs add column if not exists safra_id bigint;
update public.ptvs p set safra_id = s.id
from public.safras s where p.safra_id is null and s.usuario_id = p.usuario_id and s.nome = '2026';

-- Bloqueia a migração se houver registros antigos sem proprietário ou safra.
do $$ begin
  if exists (select 1 from public.ptvs where usuario_id is null or safra_id is null) then
    raise exception 'Existem PTVs sem proprietário ou safra. Corrija esses registros antes de executar a migração.';
  end if;
end $$;
alter table public.ptvs alter column usuario_id set not null;
alter table public.ptvs alter column safra_id set not null;
alter table public.ptvs drop constraint if exists ptvs_safra_usuario_fk;
alter table public.ptvs add constraint ptvs_safra_usuario_fk foreign key (safra_id, usuario_id) references public.safras(id, usuario_id);
create index if not exists ptvs_safra_id_idx on public.ptvs(safra_id);

create or replace function public.definir_safra_padrao(safra bigint)
returns void language plpgsql security invoker set search_path = '' as $$
begin
  if not exists (select 1 from public.safras where id = safra and usuario_id = auth.uid()) then
    raise exception 'Safra não encontrada';
  end if;
  update public.safras set padrao = false where usuario_id = auth.uid() and padrao;
  update public.safras set padrao = true where id = safra and usuario_id = auth.uid();
end $$;
revoke all on function public.definir_safra_padrao(bigint) from public, anon;
grant execute on function public.definir_safra_padrao(bigint) to authenticated;

create or replace function public.salvar_ptv(dados jsonb, produtos jsonb)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare novo_id bigint; item jsonb; posicao integer := 0; safra bigint;
begin
  if auth.uid() is null then raise exception 'Login necessario'; end if;
  safra := nullif(dados->>'safra_id', '')::bigint;
  if not exists (select 1 from public.safras where id = safra and usuario_id = auth.uid()) then
    raise exception 'Safra não encontrada';
  end if;
  insert into public.ptvs (safra_id, numero_ptv, nome_destinatario, cpf_cnpj_destinatario,
    endereco_destino, municipio_destino, uf_destino, data_emissao, data_validade, nota_fiscal)
  values (safra, dados->>'numero_ptv', dados->>'nome_destinatario', dados->>'cpf_cnpj_destinatario',
    dados->>'endereco_destino', dados->>'municipio_destino', dados->>'uf_destino',
    nullif(dados->>'data_emissao','')::date, nullif(dados->>'data_validade','')::date, dados->>'nota_fiscal')
  returning id into novo_id;
  for item in select * from jsonb_array_elements(produtos) loop
    posicao := posicao + 1;
    insert into public.ptv_produtos (ptv_id, ordem, quantidade, documento_origem, numero_documento)
    values (novo_id, posicao, nullif(item->>'quantidade','')::numeric, item->>'documento_origem', item->>'numero_documento');
  end loop;
  return novo_id;
end $$;
revoke all on function public.salvar_ptv(jsonb, jsonb) from public, anon;
grant execute on function public.salvar_ptv(jsonb, jsonb) to authenticated;
commit;
