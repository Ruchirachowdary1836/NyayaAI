from __future__ import annotations

from collections.abc import Callable

import numpy as np

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Hit

Encoder = Callable[[list[str]], np.ndarray]


class DenseRetriever:
    name = "dense"

    def __init__(
        self,
        chunks: list[LegalChunk],
        model_name: str = "BAAI/bge-m3",
        encoder: Encoder | None = None,
    ) -> None:
        self.chunks = chunks
        self.model_name = model_name
        self._encoder = encoder
        self._vectors: np.ndarray | None = None
        self._faiss_index = None
        if chunks and encoder is not None:
            self._vectors = self._normalize(encoder([chunk.text for chunk in chunks]))
            self._build_faiss_index()
        elif chunks:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise RuntimeError(
                    "Dense retrieval requires sentence-transformers; install project dependencies."
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

            self._encoder = encode
            self._vectors = self._normalize(encode([chunk.text for chunk in chunks]))
            self._build_faiss_index()

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
                for index, score in zip(indices[0], distances[0])
                if index >= 0
            ]
        else:
            scores = self._vectors @ query_vector
            ranked = [
                (index, float(scores[index]))
                for index in sorted(
                    range(len(scores)), key=lambda index: (-float(scores[index]), index)
                )[:k]
            ]
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
