"""
pavs_md.py
-----------
Funciones compartidas para generar el Markdown mensual de alertas PAVS
(data/md/pavs/AAAA-MM.md + README.md). Las usan export_markdown.py (desde
Supabase, flujo diario) y 1_convert_xlsx.py (desde un xlsx, uso manual).
"""

import hashlib
import os
import re

MD_DIR = os.path.join("data", "md", "pavs")
MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


def make_record_id(row: dict) -> str:
    """ID estable para dedupe: usa el enlace si existe, si no un hash del
    contenido (fecha + agencia + título)."""
    enlace = (row.get("enlace") or "").strip()
    if enlace:
        return hashlib.sha1(enlace.encode("utf-8")).hexdigest()
    fallback = f"{row.get('fecha_emision')}|{row.get('agencia')}|{row.get('titulo_alerta')}"
    return hashlib.sha1(fallback.encode("utf-8")).hexdigest()


def _md(v):
    """Texto de una celda en una sola línea, sin caracteres que rompan el Markdown."""
    if v is None:
        return ""
    return " ".join(str(v).replace("|", "/").split())


def escribir_markdown(records, fuente):
    """`fuente`: texto que se muestra en el índice como origen de los datos."""
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
                  f"> FT-95 Monitoreo de Alertas de PAVS · {len(filas)} alerta(s) · generado por el pipeline PAVS_Digemid",
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
              f"- **Origen:** {fuente}", "",
              "| Mes | Alertas |", "|---|---|"]
    for clave in sorted(por_mes, reverse=True):
        indice.append(f"| [{clave}]({clave}.md) | {len(por_mes[clave])} |")
    with open(os.path.join(MD_DIR, "README.md"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(indice) + "\n")
    return len(vigentes)
