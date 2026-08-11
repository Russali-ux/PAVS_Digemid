"""
2_generate_embeddings.py
--------------------------
Lee data/json/PAVS_BD_latest.json, arma un texto representativo de cada
alerta (título + producto + reacción + agencia + país) y genera su embedding
con un modelo LOCAL de sentence-transformers -- no requiere API key ni
tiene costo. La primera vez que corras esto, descarga el modelo (~470 MB)
y lo cachea en ~/.cache/huggingface; las siguientes corridas son offline.

Modelo: paraphrase-multilingual-MiniLM-L12-v2 (384 dimensiones, soporta
español). Así está definida la columna `embedding vector(384)` en Supabase.

Uso:
    pip install sentence-transformers
    python scripts/2_generate_embeddings.py
"""

import json
import os
import sys

from sentence_transformers import SentenceTransformer

JSON_IN = os.path.join("data", "json", "PAVS_BD_latest.json")
JSON_OUT = os.path.join("data", "json", "PAVS_BD_embedded.json")

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
BATCH_SIZE = 64


def build_text(rec: dict) -> str:
    parts = [
        rec.get("titulo_alerta"),
        rec.get("tipo_producto"),
        rec.get("ifa"),
        rec.get("reaccion_adversa"),
        rec.get("agencia"),
        rec.get("pais"),
    ]
    return " | ".join(p for p in parts if p)


def main():
    if not os.path.exists(JSON_IN):
        sys.exit(f"No existe {JSON_IN}. Corre primero 1_convert_xlsx.py")

    with open(JSON_IN, "r", encoding="utf-8") as f:
        records = json.load(f)

    print(f"Cargando modelo local {MODEL_NAME} (primera vez descarga ~470MB)...")
    model = SentenceTransformer(MODEL_NAME)

    print(f"Generando embeddings para {len(records)} alertas...")
    texts = [build_text(r) for r in records]
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    for rec, emb in zip(records, embeddings):
        rec["embedding"] = emb.tolist()

    with open(JSON_OUT, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False)

    print(f"OK -> {JSON_OUT}")


if __name__ == "__main__":
    main()
