"""
0_fetch_from_onedrive.py
--------------------------
Lista los .xlsx en la carpeta OneDrive "Reportes PAVS" (vía rclone, remote
"onedrive:") y descarga a data/raw/ SOLO el snapshot más reciente (por la fecha
AAAA-MM-DD del nombre): cada snapshot trae el histórico completo, así que no hace
falta bajar los demás. Con --todos descarga todos los que falten (comportamiento anterior).

Los .xlsx ya NO se versionan en el repo (solo el Markdown de data/md/): la fuente
de verdad de los Excel es OneDrive.

Requiere que `rclone` esté instalado y configurado con un remote llamado
"onedrive" (ver README.md -> "Configurar acceso a OneDrive (una sola vez)").

Uso:
    python scripts/0_fetch_from_onedrive.py
    python scripts/0_fetch_from_onedrive.py --remote-path "Documents/Claude/Projects/Reportes PAVS"
"""

import argparse
import json
import os
import re
import subprocess
import sys

RAW_DIR = os.path.join("data", "raw")
DEFAULT_REMOTE_PATH = "Documentos/Claude/Projects/Reportes PAVS"
REMOTE_NAME = "onedrive"


def rclone_lsjson(remote_path: str) -> list:
    remote = f"{REMOTE_NAME}:{remote_path}"
    try:
        out = subprocess.run(
            ["rclone", "lsjson", remote],
            capture_output=True, text=True, check=True, timeout=120,
        )
    except FileNotFoundError:
        sys.exit("rclone no está instalado en este runner/máquina.")
    except subprocess.CalledProcessError as e:
        sys.exit(f"rclone lsjson falló:\n{e.stderr}")
    return json.loads(out.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-path", default=DEFAULT_REMOTE_PATH,
                         help="Ruta dentro del remote 'onedrive:' donde están los xlsx")
    parser.add_argument("--todos", action="store_true",
                        help="Descargar todos los xlsx que falten (por defecto: solo el más reciente)")
    args = parser.parse_args()

    os.makedirs(RAW_DIR, exist_ok=True)

    items = rclone_lsjson(args.remote_path)
    remote_xlsx = [i["Name"] for i in items if not i.get("IsDir") and i["Name"].lower().endswith(".xlsx")]

    if not remote_xlsx:
        sys.exit(f"No se encontraron .xlsx en onedrive:{args.remote_path}")

    if not args.todos:
        # Solo snapshots "FT-95 ... PAVS_AAAA-MM-DD.xlsx"; el más reciente por fecha del nombre
        fechados = sorted(
            (m.group(1), n) for n in remote_xlsx
            if "PAVS" in n.upper() and (m := re.search(r"(\d{4}-\d{2}-\d{2})", n))
        )
        if not fechados:
            sys.exit("No se encontró ningún snapshot 'FT-95 ... PAVS_AAAA-MM-DD.xlsx' en OneDrive")
        remote_xlsx = [fechados[-1][1]]
        print(f"Snapshot más reciente en OneDrive: {remote_xlsx[0]}")

    local_existing = set(os.listdir(RAW_DIR))
    to_download = [name for name in remote_xlsx if name not in local_existing]

    if not to_download:
        print("No hay archivos nuevos -- data/raw/ ya tiene todo lo que hay en OneDrive.")
        return

    print(f"Descargando {len(to_download)} archivo(s) nuevo(s):")
    for name in to_download:
        remote_file = f"{REMOTE_NAME}:{args.remote_path}/{name}"
        print(f"  - {name}")
        subprocess.run(
            ["rclone", "copyto", remote_file, os.path.join(RAW_DIR, name)],
            check=True,
        )

    print("OK -- descarga completa.")


if __name__ == "__main__":
    main()
