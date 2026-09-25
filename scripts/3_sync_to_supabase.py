"""
3_sync_to_supabase.py
------------------------
Sube (upsert) data/json/PAVS_BD_embedded.json a la tabla public.pavs_alertas
del proyecto Supabase, usando el REST API (PostgREST) con la service_role
key. El upsert usa `enlace` como clave de conflicto -- así, correr esto
varios días seguidos no duplica alertas, solo agrega las nuevas.

Si no corriste 2_generate_embeddings.py, puedes subir sin la columna
`embedding` usando --skip-embeddings (útil para probar el resto del pipeline
sin gastar cuota de OpenAI).

Requiere las variables de entorno:
    SUPABASE_URL                 (ej. https://ggbnfdaxtsngsjssrwrl.supabase.co)
    SUPABASE_SERVICE_ROLE_KEY    (Settings -> API -> service_role, NUNCA la anon key)

Uso:
    export SUPABASE_URL=https://ggbnfdaxtsngsjssrwrl.supabase.co
    export SUPABASE_SERVICE_ROLE_KEY=...
    python scripts/3_sync_to_supabase.py
    python scripts/3_sync_to_supabase.py --skip-embeddings
"""

import argparse
import hashlib
import json
import os
import sys

import requests

JSON_EMBEDDED = os.path.join("data", "json", "PAVS_BD_embedded.json")
JSON_PLAIN = os.path.join("data", "json", "PAVS_BD_latest.json")

TABLE = "pavs_alertas"
BATCH_SIZE = 200

FIELDS = [
    "anio", "mes", "fecha_emision", "fecha_revision", "pais", "agencia",
    "tipo_alerta", "titulo_alerta", "tipo_producto", "ifa", "reaccion_adversa",
    "enlace", "fuente_archivo", "embedding", "dedupe_key",
]


def make_dedupe_key(rec: dict) -> str:
    """Clave única por FILA (no por enlace): un mismo boletín (p.ej. AEMPS
    mensual) trae varias alertas con el mismo enlace. Debe coincidir con la
    fórmula SQL usada en el backfill: md5 de enlace|titulo|ifa|reaccion
    normalizados (trim + lower, null -> '')."""
    partes = [rec.get(k) for k in ("enlace", "titulo_alerta", "ifa", "reaccion_adversa")]
    norm = "|".join(("" if v is None else str(v)).strip().lower() for v in partes)
    return hashlib.md5(norm.encode("utf-8")).hexdigest()
# nota: "id" no se sube -- es uuid autogenerado por Supabase. El dedupe/upsert
# se hace por `dedupe_key` (on_conflict=dedupe_key), no por id.


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-embeddings", action="store_true",
                         help="Sube sin generar/usar embeddings")
    args = parser.parse_args()

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en el entorno.")

    src = JSON_PLAIN if args.skip_embeddings else JSON_EMBEDDED
    if not os.path.exists(src):
        if args.skip_embeddings:
            sys.exit(f"No existe {src}. Corre primero 1_convert_xlsx.py")
        sys.exit(f"No existe {src}. Corre primero 2_generate_embeddings.py "
                  f"(o usa --skip-embeddings)")

    with open(src, "r", encoding="utf-8") as f:
        records = json.load(f)

    # Dedupe por dedupe_key (enlace + título + IFA + reacción). Varias alertas
    # pueden compartir enlace (boletines); solo se descartan filas idénticas,
    # que Postgres rechazaría en el mismo lote (error 21000).
    deduped = {}
    for rec in records:
        rec["dedupe_key"] = make_dedupe_key(rec)
        deduped[rec["dedupe_key"]] = rec
    n_antes = len(records)
    records = list(deduped.values())
    if len(records) < n_antes:
        print(f"Nota: se descartaron {n_antes - len(records)} filas idénticas.")

    payload_records = []
    for rec in records:
        row = {k: rec.get(k) for k in FIELDS if k in rec or k == "embedding"}
        if args.skip_embeddings:
            row.pop("embedding", None)
        payload_records.append(row)

    endpoint = f"{url.rstrip('/')}/rest/v1/{TABLE}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    print(f"Subiendo {len(payload_records)} alertas a {TABLE} (on_conflict=dedupe_key)...")

    for i in range(0, len(payload_records), BATCH_SIZE):
        batch = payload_records[i : i + BATCH_SIZE]
        resp = requests.post(
            f"{endpoint}?on_conflict=dedupe_key",
            headers=headers,
            data=json.dumps(batch),
            timeout=60,
        )
        if resp.status_code >= 300:
            print(resp.text)
            resp.raise_for_status()
        print(f"  {min(i + BATCH_SIZE, len(payload_records))}/{len(payload_records)}")

    print("OK - sincronizado con Supabase.")


if __name__ == "__main__":
    main()
