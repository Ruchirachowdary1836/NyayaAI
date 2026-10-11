"""Precompute the dense-retrieval embedding cache for the processed corpus.

The API reuses ``data/indices/dense-<model>-<fingerprint>.npy`` whenever the model and
chunk texts are unchanged, so running this once avoids embedding the corpus on the
first dense or hybrid request. Re-run after re-ingesting or changing EMBEDDING_MODEL.

    python scripts/build_dense_index.py
"""

from __future__ import annotations

import argparse
import logging
import time

from backend.app.core.config import settings
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.service import load_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--chunks", default=settings.data_chunks_path)
    parser.add_argument("--model", default=settings.embedding_model)
    parser.add_argument("--index-dir", default=settings.index_dir)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    chunks = load_chunks(args.chunks)
    if not chunks:
        raise SystemExit(f"No chunks found at {args.chunks}; run ingestion first.")
    started = time.perf_counter()
    retriever = DenseRetriever(chunks, model_name=args.model, cache_dir=args.index_dir)
    elapsed = time.perf_counter() - started
    source = "reused existing cache" if retriever.loaded_from_cache else "computed embeddings"
    print(f"{source}: {len(chunks)} chunks, model={args.model}, {elapsed:.1f}s")
    print(f"cache file: {retriever.cache_path}")


if __name__ == "__main__":
    main()
