-- Estrutura inicial para PTVs. Execute no SQL Editor do projeto Supabase.
-- O RLS permanece habilitado e sem politicas publicas ate definirmos o login.
begin;

create table if not exists public.ptvs (
    id bigint generated always as identity primary key,
    numero_ptv text not null unique,
    nome_remetente text,
    cpf_cnpj_remetente text,
    endereco_origem text,
    municipio_origem text,
    uf_origem text,
    nome_destinatario text,
    cpf_cnpj_destinatario text,
    endereco_destino text,
    municipio_destino text,
    uf_destino text,
    data_emissao date,
    data_validade date,
    itinerario text,
    nota_fiscal text,
    declaracao_adicional text,
    criado_em timestamptz not null default now(),
    atualizado_em timestamptz not null default now()
);

create table if not exists public.ptv_produtos (
    id bigint generated always as identity primary key,
    ptv_id bigint not null references public.ptvs(id) on delete cascade,
    ordem integer not null check (ordem > 0),
    produto text,
    nome_vulgar text,
    nome_cientifico text,
    cultivar text,
    unidade_producao text,
    quantidade numeric check (quantidade >= 0),
    medida text,
    documento_origem text,
    numero_documento text,
    unique (ptv_id, ordem)
);

create index if not exists ptvs_data_emissao_idx on public.ptvs (data_emissao);
create index if not exists ptvs_destinatario_idx on public.ptvs (nome_destinatario);

alter table public.ptvs enable row level security;
alter table public.ptv_produtos enable row level security;

commit;
