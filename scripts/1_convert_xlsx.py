"""
1_convert_xlsx.py
------------------
Toma el archivo .xlsx "FT-95 Monitoreo de Alertas de PAVS_YYYY-MM-DD.xlsx" más
reciente dentro de data/raw/, lee la hoja PAVS_BD (la tabla acumulada de
alertas) y genera:

  - data/csv/PAVS_BD_latest.csv    (no versionado)
  - data/json/PAVS_BD_latest.json  (no versionado)
  - data/md/pavs/AAAA-MM.md        (VERSIONADO: un archivo por mes, una sección por alerta)
  - data/md/pavs/README.md         (índice: meses, conteos, última alerta)

El Markdown es liviano (~1 MB para todo el histórico frente a ~0.6 MB por cada xlsx
diario), legible en GitHub y sus cambios diarios solo tocan el mes en curso. También
es la fuente de texto para la búsqueda de alertas en ConkoSafe IA.

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
MD_DIR = os.path.join("data", "md", "pavs")
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
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


def _md(v):
    """Texto de una celda en una sola línea, sin caracteres que rompan el Markdown."""
    if v is None:
        return ""
    return " ".join(str(v).replace("|", "/").split())


def escribir_markdown(records, fuente):
    """Un .md por mes (AAAA-MM) + índice. Salida determinística: sin marcas de tiempo,
    así el commit diario solo incluye los meses que realmente cambiaron."""
    os.makedirs(MD_DIR, exist_ok=True)
    por_mes = {}
    for r in records:
        f = r.get("fecha_emision") or ""
        if re.match(r"\d{4}-\d{2}", str(f)):
            clave = str(f)[:7]
        elif r.get("anio") and r.get("mes"):
            try:
                clave = f"{int(r['anio']):04d}-{int(r['mes']):02d}"
            except (TypeError, ValueError):
                clave = "sin-fecha"
        else:
            clave = "sin-fecha"
        por_mes.setdefault(clave, []).append(r)

    vigentes = set()
    for clave, filas in sorted(por_mes.items()):
        filas.sort(key=lambda r: (str(r.get("fecha_emision") or ""), _md(r.get("agencia")), _md(r.get("titulo_alerta"))))
        if clave == "sin-fecha":
            titulo = "Alertas PAVS sin fecha de emisión"
        else:
            a, m = clave.split("-")
            titulo = f"Alertas PAVS — {MESES[int(m)].capitalize()} {a}"
        lineas = [f"# {titulo}", "",
                  f"> FT-95 Monitoreo de Alertas de PAVS · {len(filas)} alerta(s) · generado desde OneDrive por el pipeline PAVS_Digemid",
                  ""]
        for r in filas:
            lineas += [
                f"## {_md(r.get('titulo_alerta')) or '(sin título)'}",
                f"<!-- id: {r['local_id']} -->",
                f"- **Fecha de emisión:** {_md(r.get('fecha_emision')) or '—'}"
                + (f" · **Revisión:** {_md(r.get('fecha_revision'))}" if r.get('fecha_revision') else ""),
                f"- **Agencia:** {_md(r.get('agencia')) or '—'} · **País:** {_md(r.get('pais')) or '—'}",
                f"- **Tipo de alerta:** {_md(r.get('tipo_alerta')) or '—'} · **Tipo de producto:** {_md(r.get('tipo_producto')) or '—'}",
                f"- **IFA / nombre genérico:** {_md(r.get('ifa')) or '—'}",
                f"- **Reacción / incidente adverso:** {_md(r.get('reaccion_adversa')) or '—'}",
                f"- **Enlace:** {_md(r.get('enlace')) or '—'}",
                "",
            ]
        nombre = f"{clave}.md"
        vigentes.add(nombre)
        with open(os.path.join(MD_DIR, nombre), "w", encoding="utf-8", newline="\n") as fh:
            fh.write("\n".join(lineas))

    # meses que ya no existen en el snapshot (p. ej. alertas reclasificadas)
    for viejo in os.listdir(MD_DIR):
        if viejo.endswith(".md") and viejo != "README.md" and viejo not in vigentes:
            os.remove(os.path.join(MD_DIR, viejo))

    ultima = max((str(r.get("fecha_emision")) for r in records if r.get("fecha_emision")), default="—")
    indice = ["# Alertas PAVS (FT-95) en Markdown", "",
              f"- **Total de alertas:** {len(records)}",
              f"- **Alerta más reciente:** {ultima}",
              f"- **Snapshot de origen:** `{fuente}` (OneDrive · Reportes PAVS)", "",
              "| Mes | Alertas |", "|---|---|"]
    for clave in sorted(por_mes, reverse=True):
        indice.append(f"| [{clave}]({clave}.md) | {len(por_mes[clave])} |")
    with open(os.path.join(MD_DIR, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(indice) + "\n")
    return len(vigentes)


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

    # Markdown (versionado)
    n = escribir_markdown(records, os.path.basename(src))
    print(f"OK -> {MD_DIR}/ ({n} archivos mensuales + README.md)")


if __name__ == "__main__":
    main()
