"""
1_convert_xlsx.py
------------------
Toma el archivo .xlsx "FT-95 Monitoreo de Alertas de PAVS_YYYY-MM-DD.xlsx" más
reciente dentro de data/raw/, lee la hoja PAVS_BD (la tabla acumulada de
alertas) y genera:

  - data/csv/PAVS_BD_latest.csv
  - data/json/PAVS_BD_latest.json

Cada snapshot xlsx que sube la tarea programada de Claude contiene el
histórico COMPLETO hasta esa fecha (no solo los registros nuevos), así que
basta con procesar el archivo más reciente por nombre de fecha en el nombre
del archivo.

Uso:
    python scripts/1_convert_xlsx.py
    python scripts/1_convert_xlsx.py --file "data/raw/FT-95 ... .xlsx"
"""

import argparse
import glob
import hashlib
import json
import os
import re
import sys
from datetime import datetime, date

import pandas as pd

RAW_DIR = os.path.join("data", "raw")
CSV_DIR = os.path.join("data", "csv")
JSON_DIR = os.path.join("data", "json")
SHEET_NAME = "PAVS_BD"

COLUMN_MAP = {
    "AÑO": "anio",
    "MES": "mes",
    "Fecha\nEmisión": "fecha_emision",
    "Fecha\nRevisión": "fecha_revision",
    "Pais": "pais",
    "Agencia": "agencia",
    "Tipo de Alerta": "tipo_alerta",
    "Titulo de Alerta": "titulo_alerta",
    "Tipo de Producto": "tipo_producto",
    "IFA / Nombre Genérico": "ifa",
    "Reacción Adversa / Incidente Adverso": "reaccion_adversa",
    "Enlace": "enlace",
}


def find_latest_xlsx(raw_dir: str) -> str:
    """Encuentra el xlsx más reciente por la fecha YYYY-MM-DD en el nombre."""
    candidates = glob.glob(os.path.join(raw_dir, "*.xlsx"))
    if not candidates:
        sys.exit(f"No se encontraron archivos .xlsx en {raw_dir}/")

    dated = []
    for path in candidates:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
        if m:
            dated.append((datetime.strptime(m.group(1), "%Y-%m-%d"), path))

    if dated:
        dated.sort(key=lambda t: t[0])
        return dated[-1][1]

    # fallback: el modificado más recientemente
    return max(candidates, key=os.path.getmtime)


def make_record_id(row: dict) -> str:
    """ID estable para dedupe: usa el enlace si existe, si no un hash del
    contenido (fecha + agencia + título)."""
    enlace = (row.get("enlace") or "").strip()
    if enlace:
        return hashlib.sha1(enlace.encode("utf-8")).hexdigest()
    fallback = f"{row.get('fecha_emision')}|{row.get('agencia')}|{row.get('titulo_alerta')}"
    return hashlib.sha1(fallback.encode("utf-8")).hexdigest()


def clean_value(v):
    if pd.isna(v):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, str):
        v = v.strip()
        return v if v else None
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", help="Ruta a un xlsx específico (opcional)")
    args = parser.parse_args()

    src = args.file or find_latest_xlsx(RAW_DIR)
    print(f"Leyendo: {src}")

    df = pd.read_excel(src, sheet_name=SHEET_NAME)
    df = df.rename(columns=COLUMN_MAP)
    df = df[[c for c in COLUMN_MAP.values() if c in df.columns]]
    df = df.dropna(how="all")
    # descarta filas sin agencia+título (encabezados repetidos / filas vacías)
    df = df.dropna(subset=["agencia", "titulo_alerta"], how="all")

    os.makedirs(CSV_DIR, exist_ok=True)
    os.makedirs(JSON_DIR, exist_ok=True)

    records = []
    for _, row in df.iterrows():
        rec = {col: clean_value(row.get(col)) for col in COLUMN_MAP.values()}
        # local_id es solo para dedupe/QA local -- NO se sube a Supabase como
        # `id` (esa columna es uuid autogenerado). El upsert real usa `enlace`.
        rec["local_id"] = make_record_id(rec)
        rec["fuente_archivo"] = os.path.basename(src)
        records.append(rec)

    # CSV
    csv_path = os.path.join(CSV_DIR, "PAVS_BD_latest.csv")
    pd.DataFrame(records).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # JSON
    json_path = os.path.join(JSON_DIR, "PAVS_BD_latest.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"OK -> {csv_path} ({len(records)} filas)")
    print(f"OK -> {json_path} ({len(records)} filas)")


if __name__ == "__main__":
    main()
