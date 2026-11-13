"""
export_markdown.py
-------------------
Regenera data/md/pavs/ (un .md por mes + README.md) a partir de la tabla
public.pavs_alertas de Supabase, que es la fuente de verdad desde que la tarea
programada carga las alertas directo ahí (noviembre 2026).

La salida es determinística: si no cambió nada en Supabase, el commit diario
no trae cambios.

Uso:
    python scripts/export_markdown.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pavs_md import MD_DIR, escribir_markdown, make_record_id  # noqa: E402
from supabase_rest import fetch_all  # noqa: E402

CAMPOS = ["anio", "mes", "fecha_emision", "fecha_revision", "pais", "agencia", "tipo_alerta",
          "titulo_alerta", "tipo_producto", "ifa", "reaccion_adversa", "enlace"]


def main():
    filas = fetch_all(",".join(CAMPOS), order="fecha_emision.asc.nullsfirst,id")
    if not filas:
        sys.exit("Supabase devolvió 0 filas: no se regenera el Markdown.")
    for r in filas:
        r["local_id"] = make_record_id(r)
    n = escribir_markdown(filas, "Supabase `public.pavs_alertas`")
    print(f"OK -> {MD_DIR}/ ({len(filas)} alertas, {n} archivos mensuales + README.md)")


if __name__ == "__main__":
    main()
