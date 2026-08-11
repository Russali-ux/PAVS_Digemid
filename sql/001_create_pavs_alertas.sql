-- 001_create_pavs_alertas.sql
-- Ya aplicada en el proyecto Supabase "Russali-ux's Project" (ggbnfdaxtsngsjssrwrl).
-- Se guarda aquí como referencia versionada / para replicar en otro proyecto.

create extension if not exists vector;

create table if not exists public.pavs_alertas (
  id uuid primary key default gen_random_uuid(),
  anio integer,
  mes integer,
  fecha_emision date,
  fecha_revision date,
  pais text,
  agencia text,
  tipo_alerta text,
  titulo_alerta text,
  tipo_producto text,
  ifa text,
  reaccion_adversa text,
  enlace text unique,
  embedding vector(384),
  fuente_archivo text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table public.pavs_alertas is 'Alertas de Países de Alta Vigilancia Sanitaria (PAVS) - reporte FT-95 / DS043, consolidado desde los Excel PAVS_BD.';

create index if not exists pavs_alertas_agencia_idx on public.pavs_alertas (agencia);
create index if not exists pavs_alertas_pais_idx on public.pavs_alertas (pais);
create index if not exists pavs_alertas_fecha_emision_idx on public.pavs_alertas (fecha_emision);
create index if not exists pavs_alertas_anio_idx on public.pavs_alertas (anio);

create index if not exists pavs_alertas_embedding_idx
  on public.pavs_alertas
  using hnsw (embedding vector_cosine_ops);

alter table public.pavs_alertas enable row level security;

create policy "pavs_alertas_select_authenticated"
  on public.pavs_alertas
  for select
  to authenticated
  using (true);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_pavs_alertas_updated_at on public.pavs_alertas;
create trigger trg_pavs_alertas_updated_at
  before update on public.pavs_alertas
  for each row execute function public.set_updated_at();

-- Función de búsqueda semántica (usada por el chatbot / ConkoSafe IA)
create or replace function public.match_pavs_alertas(
  query_embedding vector(384),
  match_count int default 10,
  filter_pais text default null,
  filter_agencia text default null
)
returns table (
  id uuid,
  titulo_alerta text,
  pais text,
  agencia text,
  fecha_emision date,
  enlace text,
  similarity float
)
language sql stable
as $$
  select
    p.id,
    p.titulo_alerta,
    p.pais,
    p.agencia,
    p.fecha_emision,
    p.enlace,
    1 - (p.embedding <=> query_embedding) as similarity
  from public.pavs_alertas p
  where p.embedding is not null
    and (filter_pais is null or p.pais = filter_pais)
    and (filter_agencia is null or p.agencia = filter_agencia)
  order by p.embedding <=> query_embedding
  limit match_count;
$$;
