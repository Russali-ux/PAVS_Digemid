# PAVS_Digemid

Pipeline del reporte **FT-95 Monitoreo de Alertas de PAVS**: las alertas viven en
Supabase (`public.pavs_alertas`, pgvector) para que ConkoSafe IA / el chatbot haga
búsqueda semántica, y el repo guarda una copia legible en Markdown mensual.

## Cómo fluyen los datos (desde el 2026-11-12)

```
Tarea programada de Claude (en la PC)
  ├─ escribe el Excel FT-95 ..._AAAA-MM-DD.xlsx en OneDrive / Reportes PAVS   (sin cambios)
  └─ carga las filas nuevas en Supabase:  select * from public.upsert_pavs_alertas('[...]'::jsonb, '<xlsx>')
                                          (embedding queda en NULL)
GitHub Action diario (12:00 Lima)
  1. scripts/embed_missing.py     -> calcula los embeddings que falten (modelo local, sin API key)
  2. scripts/export_markdown.py   -> regenera data/md/pavs/ desde Supabase y commitea si cambió
```

**Por qué cambió:** el 2026-11-12 OneDrive empezó a rechazar todas las descargas por API
de la cuenta (listar sí funciona; descargar devuelve `401 BadContextToken`, también con curl y
token recién renovado). El Action ya no descarga nada de OneDrive ni necesita `RCLONE_CONF`.

## Estructura del repo

```
PAVS_Digemid/
├── .github/workflows/sync-pavs.yml   # diario 12:00 Lima (o manual)
├── data/md/pavs/                     # VERSIONADO: un Markdown por mes (AAAA-MM.md) + README.md
├── scripts/
│   ├── embed_missing.py              # flujo diario: embeddings faltantes en Supabase
│   ├── export_markdown.py            # flujo diario: Supabase -> Markdown
│   ├── pavs_md.py, supabase_rest.py  # utilidades compartidas
│   ├── 1_convert_xlsx.py             # manual: xlsx -> csv/json/markdown
│   ├── 2_generate_embeddings.py      # manual: embeddings de todo el json
│   └── 3_sync_to_supabase.py         # manual: carga completa json -> Supabase
├── sql/
│   ├── 001_create_pavs_alertas.sql   # esquema
│   └── 002_upsert_pavs_alertas.sql   # función de carga directa (la usa la tarea programada)
└── requirements.txt
```

Secretos del Action: `SUPABASE_URL` y `SUPABASE_SERVICE_ROLE_KEY`. El secreto `RCLONE_CONF`
ya no se usa y se puede borrar.

## Carga completa desde un Excel (recuperación / backfill)

Si alguna vez hace falta reconstruir la tabla desde un snapshot (cada xlsx trae el
histórico completo en la hoja `PAVS_BD`): copiarlo a `data/raw/` y correr los pasos
manuales `1_convert_xlsx.py` -> `2_generate_embeddings.py` -> `3_sync_to_supabase.py`
(ver abajo). El upsert usa `dedupe_key`, así que no duplica filas.

## Cómo funciona el resto del pipeline

Cada snapshot `.xlsx` que se sube contiene el histórico **completo** hasta
esa fecha (no solo lo nuevo del día), en la hoja `PAVS_BD`. Por eso el
paso de conversión siempre toma el archivo más reciente por la fecha en su
nombre, no acumula archivo por archivo.

1. **Convertir** (`1_convert_xlsx.py`): lee `PAVS_BD`, normaliza columnas y
   genera `PAVS_BD_latest.csv` / `.json`. A cada fila le calcula un `local_id`
   estable (hash del enlace, solo para debug local) -- el dedupe real en
   Supabase se hace por `enlace`, no por este campo.
2. **Generar embeddings** (`2_generate_embeddings.py`): arma un texto por
   alerta (título + producto + IFA + reacción + agencia + país) y genera su
   embedding con un modelo **local** de sentence-transformers
   (`paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensiones, soporta
   español) -- no requiere API key ni tiene costo.
3. **Sincronizar con Supabase** (`3_sync_to_supabase.py`): hace upsert a
   `public.pavs_alertas` usando `enlace` como clave de conflicto -- correrlo
   varias veces no duplica filas, solo agrega/actualiza.

## Por qué pgvector + embeddings locales (sin Pinecone ni OpenAI)

Tu proyecto Supabase ya tenía la extensión `vector` disponible. Se activó y
se creó la columna `embedding vector(384)` + un índice HNSW sobre
`public.pavs_alertas`, así que la búsqueda semántica vive en la misma base
de datos -- sin depender de Pinecone ni de una segunda fuente de verdad. Y
para no depender de una API de pago, los embeddings se generan con un
modelo local de sentence-transformers (gratis). La función
`match_pavs_alertas(query_embedding, match_count, filter_pais,
filter_agencia)` ya quedó creada para hacer la búsqueda por similitud
(coseno) desde el backend o desde una Edge Function.

Ya se probó de punta a punta: se insertaron alertas reales con su embedding
generado localmente y `match_pavs_alertas()` las encontró correctamente por
similitud.

## Esquema de la tabla `public.pavs_alertas`

| Columna            | Tipo         | Notas                                   |
|--------------------|--------------|------------------------------------------|
| id                 | uuid (PK)    | generado por Supabase                    |
| anio, mes          | integer      |                                            |
| fecha_emision      | date         |                                            |
| fecha_revision     | date         |                                            |
| pais               | text         |                                            |
| agencia            | text         | AEMPS, FDA, MHRA, DIGEMID, CENADIM, ...  |
| tipo_alerta        | text         |                                            |
| titulo_alerta      | text         |                                            |
| tipo_producto      | text         |                                            |
| ifa                | text         | IFA / Nombre genérico                    |
| reaccion_adversa   | text         |                                            |
| enlace             | text         |                                            |
| dedupe_key         | text (UNIQUE)| md5(enlace/título/IFA/reacción): clave de upsert |
| embedding          | vector(384)  | modelo local, gratis                     |
| fuente_archivo     | text         | nombre del xlsx de origen                |
| created_at/updated_at | timestamptz | automáticos                            |

RLS está activo con una policy de solo lectura para usuarios `authenticated`;
las escrituras (upsert) se hacen con la `service_role` key, que ignora RLS.

## Correrlo manualmente (sin esperar al cron)

```bash
pip install -r requirements.txt
cp .env.example .env   # completa SUPABASE_SERVICE_ROLE_KEY

# flujo diario
export $(grep -v '^#' .env | xargs)
python scripts/embed_missing.py
python scripts/export_markdown.py

# carga completa desde un xlsx copiado a data/raw/
python scripts/1_convert_xlsx.py
python scripts/2_generate_embeddings.py
python scripts/3_sync_to_supabase.py
```

En GitHub también puedes lanzarlo a mano: pestaña **Actions -> Sync PAVS
(Supabase -> embeddings -> Markdown) -> Run workflow**.

## Notas

- La hoja `2021` de los Excel es un histórico legacy en formato distinto;
  su contenido ya está incluido dentro de `PAVS_BD` (se verificó que los años
  2019–2026 están todos en esa hoja), por eso el pipeline solo lee `PAVS_BD`.
- La hoja `DS043` es la ficha de referencia del documento (código, versión,
  vigencia, lista de agencias) -- no son datos de alertas, no se procesa.
- Los secretos (`SUPABASE_SERVICE_ROLE_KEY`) **nunca** deben
  subirse al repo; solo van en GitHub Secrets o en tu `.env` local (ya está
  en `.gitignore`).
- El modelo de embeddings descarga sus pesos de Hugging Face la primera vez
  que corre; el workflow los cachea (`actions/cache`) para no volver a
  descargarlos cada día.
- Si el nombre del xlsx deja de traer la fecha en `YYYY-MM-DD`, ajusta
  `find_latest_xlsx()` en `1_convert_xlsx.py` (solo afecta la carga manual).
