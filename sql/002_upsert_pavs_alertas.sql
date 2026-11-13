-- 002_upsert_pavs_alertas.sql  (aplicada el 2026-11-12 como migración "pavs_upsert_function")
-- Carga directa de filas PAVS_BD desde la tarea programada:
--   select * from public.upsert_pavs_alertas('[{...fila...}, ...]'::jsonb, 'FT-95 ..._AAAA-MM-DD.xlsx');
-- Campos de cada objeto: anio, mes, fecha_emision (AAAA-MM-DD), fecha_revision, pais, agencia,
-- tipo_alerta, titulo_alerta, tipo_producto, ifa, reaccion_adversa, enlace.
-- dedupe_key = md5(enlace|titulo|ifa|reaccion) con trim+lower y null -> '' (igual que 3_sync_to_supabase.py),
-- así que reenviar filas ya cargadas no duplica nada. Devuelve (insertadas, actualizadas).
-- Las filas nuevas quedan con embedding NULL; el Action las completa con scripts/embed_missing.py.
-- Solo service_role (y el rol postgres del MCP) pueden ejecutarla.

create or replace function public.upsert_pavs_alertas(p_rows jsonb, p_fuente text default null)
returns table (insertadas int, actualizadas int)
language plpgsql
set search_path = public
as $$
declare v_ins int := 0; v_upd int := 0;
begin
  with src as (
    select
      nullif(trim(r->>'anio'),'')::numeric::int  as anio,
      nullif(trim(r->>'mes'),'')::numeric::int   as mes,
      nullif(trim(r->>'fecha_emision'),'')::date  as fecha_emision,
      nullif(trim(r->>'fecha_revision'),'')::date as fecha_revision,
      nullif(trim(r->>'pais'),'') as pais,
      nullif(trim(r->>'agencia'),'') as agencia,
      nullif(trim(r->>'tipo_alerta'),'') as tipo_alerta,
      nullif(trim(r->>'titulo_alerta'),'') as titulo_alerta,
      nullif(trim(r->>'tipo_producto'),'') as tipo_producto,
      nullif(trim(r->>'ifa'),'') as ifa,
      nullif(trim(r->>'reaccion_adversa'),'') as reaccion_adversa,
      nullif(trim(r->>'enlace'),'') as enlace
    from jsonb_array_elements(p_rows) r
  ), keyed as (
    select distinct on (k) *, md5(
      lower(coalesce(enlace,''))||'|'||lower(coalesce(titulo_alerta,''))||'|'||
      lower(coalesce(ifa,''))||'|'||lower(coalesce(reaccion_adversa,''))) as k
    from src
    where coalesce(agencia, titulo_alerta) is not null
  ), up as (
    insert into public.pavs_alertas as t
      (anio, mes, fecha_emision, fecha_revision, pais, agencia, tipo_alerta, titulo_alerta,
       tipo_producto, ifa, reaccion_adversa, enlace, fuente_archivo, dedupe_key)
    select anio, mes, fecha_emision, fecha_revision, pais, agencia, tipo_alerta, titulo_alerta,
           tipo_producto, ifa, reaccion_adversa, enlace, p_fuente, k
    from keyed
    on conflict (dedupe_key) do update set
      anio = excluded.anio, mes = excluded.mes, fecha_emision = excluded.fecha_emision,
      fecha_revision = excluded.fecha_revision, pais = excluded.pais, agencia = excluded.agencia,
      tipo_alerta = excluded.tipo_alerta, tipo_producto = excluded.tipo_producto,
      fuente_archivo = coalesce(excluded.fuente_archivo, t.fuente_archivo),
      -- si cambia el texto que entra al embedding, se recalcula
      embedding = case when (t.tipo_producto, t.agencia, t.pais) is distinct from
                            (excluded.tipo_producto, excluded.agencia, excluded.pais)
                       then null else t.embedding end
    returning (xmax = 0) as nueva
  )
  select count(*) filter (where nueva), count(*) filter (where not nueva) into v_ins, v_upd from up;
  return query select v_ins, v_upd;
end $$;

revoke all on function public.upsert_pavs_alertas(jsonb, text) from public, anon, authenticated;
grant execute on function public.upsert_pavs_alertas(jsonb, text) to service_role;
