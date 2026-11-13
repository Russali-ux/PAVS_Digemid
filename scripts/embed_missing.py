"""
embed_missing.py
-----------------
Completa la columna `embedding` de public.pavs_alertas para las filas que
llegaron sin ella (las inserta la tarea programada con
public.upsert_pavs_alertas, que deja embedding = NULL).

Usa el mismo modelo local y el mismo texto que 2_generate_embeddings.py, así
que los vectores son comparables con los ya existentes. Si no hay filas
pendientes, termina sin descargar el modelo.

Uso:
    python scripts/embed_missing.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from supabase_rest import fetch_all, patch_by_id  # noqa: E402

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
CAMPOS_TEXTO = ["titulo_alerta", "tipo_producto", "ifa", "reaccion_adversa", "agencia", "pais"]


def build_text(rec: dict) -> str:
    # Debe coincidir con build_text() de 2_generate_embeddings.py
    return " | ".join(rec[c] for c in CAMPOS_TEXTO if rec.get(c))


def main():
    pendientes = fetch_all("id," + ",".join(CAMPOS_TEXTO), {"embedding": "is.null"})
    if not pendientes:
        print("No hay filas sin embedding.")
        return

    print(f"{len(pendientes)} fila(s) sin embedding. Cargando modelo {MODEL_NAME}...")
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)
    vectores = model.encode([build_text(r) for r in pendientes], batch_size=64,
                            normalize_embeddings=True, show_progress_bar=False)

    for rec, emb in zip(pendientes, vectores):
        patch_by_id(rec["id"], {"embedding": emb.tolist()})
    print(f"OK -- {len(pendientes)} embedding(s) guardados en Supabase.")


if __name__ == "__main__":
    main()
