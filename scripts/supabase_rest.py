"""
supabase_rest.py
-----------------
Helpers mínimos para hablar con PostgREST de Supabase usando la service_role key.

Variables de entorno requeridas:
    SUPABASE_URL                 (ej. https://ggbnfdaxtsngsjssrwrl.supabase.co)
    SUPABASE_SERVICE_ROLE_KEY    (Settings -> API -> service_role, NUNCA la anon key)
"""

import os
import sys

import requests

TABLE = "pavs_alertas"
PAGE = 1000  # límite por defecto de PostgREST


def config():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        sys.exit("Faltan SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY en el entorno.")
    endpoint = f"{url.rstrip('/')}/rest/v1/{TABLE}"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    return endpoint, headers


def fetch_all(select: str, filters: dict | None = None, order: str = "id") -> list:
    """Trae todas las filas paginando de a PAGE (orden estable por `order`)."""
    endpoint, headers = config()
    rows, offset = [], 0
    while True:
        params = {"select": select, "order": order, "limit": PAGE, "offset": offset}
        params.update(filters or {})
        r = requests.get(endpoint, headers=headers, params=params, timeout=60)
        if r.status_code >= 300:
            print(r.text)
            r.raise_for_status()
        lote = r.json()
        rows.extend(lote)
        if len(lote) < PAGE:
            return rows
        offset += PAGE


def patch_by_id(row_id: str, data: dict) -> None:
    endpoint, headers = config()
    r = requests.patch(endpoint, headers={**headers, "Prefer": "return=minimal"},
                       params={"id": f"eq.{row_id}"}, json=data, timeout=60)
    if r.status_code >= 300:
        print(r.text)
        r.raise_for_status()
