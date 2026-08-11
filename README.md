# PAVS_Digemid

Pipeline **automático diario** que trae el reporte FT-95 Monitoreo de
Alertas de PAVS desde OneDrive, lo convierte a CSV/JSON, genera embeddings
(locales, gratis) y lo sincroniza con Supabase (pgvector) para que ConkoSafe
IA / el chatbot pueda hacer búsqueda semántica sobre las alertas.

## Estructura del repo

```
PAVS_Digemid/
├── .github/workflows/
│   └── sync-pavs.yml            # corre todos los días (o manual)
├── data/
│   ├── raw/     -> .xlsx traídos de OneDrive (SÍ se versionan -- "Raw data")
│   ├── csv/     -> salida: PAVS_BD_latest.csv (generado, no versionado)
│   └── json/    -> salida: PAVS_BD_latest.json / PAVS_BD_embedded.json (generado, no versionado)
├── scripts/
│   ├── 0_fetch_from_onedrive.py # trae los xlsx nuevos desde OneDrive (rclone)
│   ├── 1_convert_xlsx.py        # xlsx -> csv + json
│   ├── 2_generate_embeddings.py # texto de cada alerta -> embedding (local, sin API key)
│   └── 3_sync_to_supabase.py    # upsert csv/json + embeddings -> Supabase
├── sql/
│   └── 001_create_pavs_alertas.sql   # esquema (ya aplicado en el proyecto)
├── requirements.txt
├── .env.example
└── .gitignore
```

## Qué hace el Action todos los días (`sync-pavs.yml`)

Corre a las **06:00 hora Perú** (11:00 UTC) y también se puede lanzar a mano
desde la pestaña *Actions* del repo (botón "Run workflow"):

1. Se conecta a tu OneDrive (carpeta `Reportes PAVS`) con `rclone` y descarga
   solo los `.xlsx` que todavía no estén en `data/raw/`.
2. Convierte el más reciente (`PAVS_BD`) a CSV/JSON.
3. Genera embeddings localmente (sin costo, sin API key).
4. Hace upsert a Supabase (`public.pavs_alertas`, dedupe por `enlace`).
5. Commitea los `.xlsx` nuevos a `data/raw/` -- así el repo queda como el
   historial versionado de "Raw data". Si no hay archivos nuevos, no
   commitea nada.

## Configurar acceso a OneDrive (una sola vez)

Para que GitHub Actions pueda leer tu carpeta de OneDrive todos los días sin
que tengas que iniciar sesión manualmente, se usa `rclone` (open source, no
requiere registrar una app en Azure). El login se hace **una sola vez, en tu
propia PC**, y genera un token que se guarda como secreto en GitHub.

1. Instala rclone en tu PC: https://rclone.org/downloads/ (en Windows, baja
   el zip, descomprime, y abre PowerShell en esa carpeta).
2. Corre:
   ```
   rclone config
   ```
   - `n` (New remote)
   - name: `onedrive`
   - type: busca y elige `onedrive` en la lista
   - client_id / client_secret: deja vacío (Enter, Enter)
   - "Edit advanced config?": `n`
   - "Use auto config?": `y` -- esto abre tu navegador, inicia sesión con tu
     cuenta (ruzph...) y autoriza.
   - Tipo de cuenta: `OneDrive Personal`
   - Elige el drive que encuentre (tu OneDrive personal)
   - Confirma con `y`, luego `q` para salir
3. Esto crea un archivo `rclone.conf` (normalmente en
   `C:\Users\ruzph\AppData\Roaming\rclone\rclone.conf` en Windows). Ábrelo
   con el Bloc de notas y copia **todo el contenido** (incluye una sección
   `[onedrive]` con `type`, `token`, etc.).
4. En GitHub: ve al repo -> **Settings -> Secrets and variables -> Actions
   -> New repository secret**, y crea:
   - `RCLONE_CONF`: pega el contenido completo del `rclone.conf`
   - `SUPABASE_URL`: `https://ggbnfdaxtsngsjssrwrl.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY`: la key de Settings -> API -> service_role
     de tu proyecto Supabase (nunca la anon key)

Con esos 3 secretos configurados, el Action ya puede correr solo. El token
de rclone se refresca automáticamente en cada corrida (Microsoft renueva el
refresh token mientras se use con cierta frecuencia -- correr a diario lo
mantiene vivo).

**Ruta en OneDrive:** el script usa por defecto
`Documentos/Claude/Projects/Reportes PAVS` (confirmado con `rclone lsjson`
-- nota que es "Documentos" en español, no "Documents"). Si mueves la
carpeta o cambia el idioma de tu OneDrive, ajústala en
`scripts/0_fetch_from_onedrive.py` (`DEFAULT_REMOTE_PATH`) o pásala como
`--remote-path` al workflow.

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
| enlace             | text (UNIQUE)| clave de dedupe/upsert                   |
| embedding          | vector(384)  | modelo local, gratis                     |
| fuente_archivo     | text         | nombre del xlsx de origen                |
| created_at/updated_at | timestamptz | automáticos                            |

RLS está activo con una policy de solo lectura para usuarios `authenticated`;
las escrituras (upsert) se hacen con la `service_role` key, que ignora RLS.

## Correrlo manualmente (sin esperar al cron)

```bash
pip install -r requirements.txt
cp .env.example .env   # completa SUPABASE_SERVICE_ROLE_KEY

# si quieres traer los xlsx de OneDrive localmente, necesitas rclone
# configurado igual que en el paso "Configurar acceso a OneDrive"
python scripts/0_fetch_from_onedrive.py

python scripts/1_convert_xlsx.py
python scripts/2_generate_embeddings.py
export $(grep -v '^#' .env | xargs)
python scripts/3_sync_to_supabase.py
```

En GitHub también puedes lanzarlo a mano: pestaña **Actions -> Sync PAVS
(OneDrive -> repo -> Supabase) -> Run workflow**.

## Notas

- La hoja `2021` de los Excel es un histórico legacy en formato distinto;
  su contenido ya está incluido dentro de `PAVS_BD` (se verificó que los años
  2019–2026 están todos en esa hoja), por eso el pipeline solo lee `PAVS_BD`.
- La hoja `DS043` es la ficha de referencia del documento (código, versión,
  vigencia, lista de agencias) -- no son datos de alertas, no se procesa.
- Los secretos (`RCLONE_CONF`, `SUPABASE_SERVICE_ROLE_KEY`) **nunca** deben
  subirse al repo; solo van en GitHub Secrets o en tu `.env` local (ya está
  en `.gitignore`).
- El modelo de embeddings descarga sus pesos de Hugging Face la primera vez
  que corre; el workflow los cachea (`actions/cache`) para no volver a
  descargarlos cada día.
- Si algún día cambias la carpeta de OneDrive o el nombre del archivo deja
  de traer la fecha en `YYYY-MM-DD`, ajusta `find_latest_xlsx()` en
  `1_convert_xlsx.py`.
