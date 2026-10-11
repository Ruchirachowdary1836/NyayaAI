from __future__ import annotations

import hashlib
import logging
import os
import re
from collections.abc import Callable
from pathlib import Path

import numpy as np

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Hit

Encoder = Callable[[list[str]], np.ndarray]
logger = logging.getLogger("nyayaai.retrieval")
_SCORE_BLOCK = 4096


def corpus_fingerprint(model_name: str, chunks: list[LegalChunk]) -> str:
    """Stable key for an embedding matrix: changes when the model or any chunk changes."""
    digest = hashlib.sha256(model_name.encode("utf-8"))
    for chunk in chunks:
        digest.update(b"\0")
        digest.update(chunk.chunk_id.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha1(chunk.text.encode("utf-8"), usedforsecurity=False).digest())
    return digest.hexdigest()


class DenseRetriever:
    name = "dense"

    def __init__(
        self,
        chunks: list[LegalChunk],
        model_name: str = "BAAI/bge-m3",
        encoder: Encoder | None = None,
        cache_dir: str | Path | None = None,
        vectors: np.ndarray | None = None,
    ) -> None:
        self.chunks = chunks
        self.model_name = model_name
        self._encoder = encoder
        self._vectors: np.ndarray | None = None
        self._faiss_index = None
        self.cache_path: Path | None = None
        self.loaded_from_cache = False
        if not chunks:
            return
        if vectors is not None:
            # Precomputed, already-normalized vectors (e.g. from an embeddings API). They are
            # kept in their stored dtype (float16) to halve memory and searched block-wise.
            if encoder is None:
                raise ValueError("A query encoder is required with precomputed vectors")
            if len(vectors) != len(chunks):
                raise ValueError("Precomputed vectors do not match the number of chunks")
            self._vectors = vectors
            self.loaded_from_cache = True
            return
        if self._encoder is None:
            self._encoder = self._load_sentence_transformer(model_name)
        if cache_dir is not None:
            safe_model = re.sub(r"[^A-Za-z0-9_.-]+", "_", model_name)
            fingerprint = corpus_fingerprint(model_name, chunks)[:20]
            self.cache_path = Path(cache_dir) / f"dense-{safe_model}-{fingerprint}.npy"
        self._vectors = self._load_cached_vectors()
        if self._vectors is None:
            self._vectors = self._normalize(self._encoder([chunk.text for chunk in chunks]))
            self._save_cached_vectors()
        self._build_faiss_index()

    @staticmethod
    def _load_sentence_transformer(model_name: str) -> Encoder:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as error:
            raise RuntimeError(
                "Dense retrieval requires the optional 'dense' dependencies "
                "(pip install -e '.[dense]')."
            ) from error
        model = SentenceTransformer(model_name)

        def encode(texts: list[str]) -> np.ndarray:
            vectors = model.encode(
                texts,
                batch_size=16,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            return np.asarray(vectors, dtype=np.float32)

        return encode

    def _load_cached_vectors(self) -> np.ndarray | None:
        if self.cache_path is None or not self.cache_path.is_file():
            return None
        try:
            vectors = np.load(self.cache_path, allow_pickle=False)
        except (OSError, ValueError):
            logger.warning("Ignoring unreadable embedding cache %s", self.cache_path.name)
            return None
        if vectors.ndim != 2 or vectors.shape[0] != len(self.chunks):
            return None
        self.loaded_from_cache = True
        logger.info("Loaded %d cached embeddings from %s", len(vectors), self.cache_path.name)
        return vectors.astype(np.float32, copy=False)

    def _save_cached_vectors(self) -> None:
        if self.cache_path is None or self._vectors is None:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.cache_path.with_suffix(".tmp.npy")
            np.save(temporary, self._vectors, allow_pickle=False)
            os.replace(temporary, self.cache_path)
        except OSError:
            logger.warning("Could not persist embedding cache to %s", self.cache_path)

    def _build_faiss_index(self) -> None:
        if self._vectors is None:
            return
        try:
            import faiss
        except ImportError:
            return
        self._faiss_index = faiss.IndexFlatIP(self._vectors.shape[1])
        self._faiss_index.add(self._vectors)

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        vectors = np.asarray(vectors, dtype=np.float32)
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.maximum(norms, 1e-12)

    def search(self, query: str, k: int = 10) -> list[Hit]:
        if k < 1:
            raise ValueError("k must be greater than zero")
        if not query.strip() or not self.chunks or self._vectors is None or self._encoder is None:
            return []
        query_vector = self._normalize(self._encoder([query]))[0]
        if self._faiss_index is not None:
            distances, indices = self._faiss_index.search(
                query_vector.reshape(1, -1), min(k, len(self.chunks))
            )
            ranked = [
                (int(index), float(score))
                for index, score in zip(indices[0], distances[0], strict=True)
                if index >= 0
            ]
        else:
            scores = np.empty(len(self._vectors), dtype=np.float32)
            # Score in blocks so float16 matrices are never fully upcast in memory.
            for start in range(0, len(self._vectors), _SCORE_BLOCK):
                block = self._vectors[start : start + _SCORE_BLOCK]
                scores[start : start + len(block)] = block.astype(np.float32) @ query_vector
            top = np.argsort(-scores, kind="stable")[:k]
            ranked = [(int(index), float(scores[index])) for index in top]
        return [
            Hit(
                doc_id=self.chunks[index].doc_id,
                chunk_id=self.chunks[index].chunk_id,
                text=self.chunks[index].text,
                score=score,
                rank=rank,
                source_scores={"dense": score},
                metadata=self.chunks[index].metadata,
            )
            for rank, (index, score) in enumerate(ranked, start=1)
        ]
