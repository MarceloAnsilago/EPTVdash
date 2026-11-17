begin;
alter table public.ptvs add column if not exists usuario_id uuid references auth.users(id);
alter table public.ptvs alter column usuario_id set default auth.uid();

create policy "ptvs_do_usuario" on public.ptvs for all to authenticated
using (usuario_id = auth.uid()) with check (usuario_id = auth.uid());
create policy "produtos_do_usuario" on public.ptv_produtos for all to authenticated
using (exists (select 1 from public.ptvs p where p.id = ptv_id and p.usuario_id = auth.uid()))
with check (exists (select 1 from public.ptvs p where p.id = ptv_id and p.usuario_id = auth.uid()));

grant select, insert, update, delete on public.ptvs, public.ptv_produtos to authenticated;
grant usage, select on sequence public.ptvs_id_seq, public.ptv_produtos_id_seq to authenticated;

create or replace function public.salvar_ptv(dados jsonb, produtos jsonb)
returns bigint language plpgsql security invoker set search_path = '' as $$
declare novo_id bigint; item jsonb; posicao integer := 0;
begin
  if auth.uid() is null then raise exception 'Login necessario'; end if;
  insert into public.ptvs (numero_ptv, nome_remetente, cpf_cnpj_remetente, endereco_origem,
    municipio_origem, uf_origem, nome_destinatario, cpf_cnpj_destinatario, endereco_destino,
    municipio_destino, uf_destino, data_emissao, data_validade, itinerario, nota_fiscal, declaracao_adicional)
  values (dados->>'numero_ptv', dados->>'nome_remetente', dados->>'cpf_cnpj_remetente', dados->>'endereco_origem',
    dados->>'municipio_origem', dados->>'uf_origem', dados->>'nome_destinatario', dados->>'cpf_cnpj_destinatario',
    dados->>'endereco_destino', dados->>'municipio_destino', dados->>'uf_destino',
    nullif(dados->>'data_emissao','')::date, nullif(dados->>'data_validade','')::date,
    dados->>'itinerario', dados->>'nota_fiscal', dados->>'declaracao_adicional') returning id into novo_id;
  for item in select * from jsonb_array_elements(produtos) loop
    posicao := posicao + 1;
    insert into public.ptv_produtos (ptv_id, ordem, produto, nome_vulgar, nome_cientifico, cultivar,
      unidade_producao, quantidade, medida, documento_origem, numero_documento)
    values (novo_id, posicao, item->>'produto', item->>'nome_vulgar', item->>'nome_cientifico', item->>'cultivar',
      item->>'unidade_producao', nullif(item->>'quantidade','')::numeric, item->>'medida', item->>'documento_origem', item->>'numero_documento');
  end loop;
  return novo_id;
end $$;
revoke all on function public.salvar_ptv(jsonb, jsonb) from public, anon;
grant execute on function public.salvar_ptv(jsonb, jsonb) to authenticated;
commit;
