from __future__ import annotations

import threading

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Retriever
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever


class RetrieverRegistry:
    _available_retrievers = ("bm25", "dense", "hybrid")

    def __init__(
        self,
        chunks: list[LegalChunk],
        embedding_model: str = "BAAI/bge-m3",
        alpha: float = 0.7,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
        enabled_retrievers: list[str] | None = None,
    ) -> None:
        enabled = (
            list(self._available_retrievers) if enabled_retrievers is None else enabled_retrievers
        )
        unknown = set(enabled) - set(self._available_retrievers)
        if unknown:
            raise ValueError(f"Unknown retrievers configured: {', '.join(sorted(unknown))}")
        self._retrievers: dict[str, Retriever] = {}
        self._chunks = chunks
        self._bm25 = BM25Retriever(chunks)
        self._retrievers["bm25"] = self._bm25
        self._enabled_retrievers = tuple(
            name for name in self._available_retrievers if name in enabled
        )
        self._dense: DenseRetriever | None = None
        self._dense_lock = threading.Lock()
        self._dense_settings = (embedding_model, alpha, fusion_method, rrf_k)

    def get(self, name: str) -> Retriever:
        if name not in self._available_retrievers:
            raise ValueError(f"Unknown retriever {name!r}; choose bm25, dense, or hybrid")
        if name not in self._enabled_retrievers:
            raise RuntimeError(f"{name.title()} retrieval is disabled by deployment configuration.")
        if (name == "dense" or name == "hybrid") and self._dense is None:
            with self._dense_lock:
                if self._dense is None:
                    model, alpha, method, rrf_k = self._dense_settings
                    dense = DenseRetriever(self._chunks, model_name=model)
                    hybrid = HybridRetriever(
                        self._bm25, dense, method=method, alpha=alpha, rrf_k=rrf_k
                    )
                    self._retrievers["dense"] = dense
                    self._retrievers["hybrid"] = hybrid
                    self._dense = dense
        return self._retrievers[name]

    @property
    def available(self) -> list[str]:
        return list(self._enabled_retrievers)

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    @property
    def document_count(self) -> int:
        return len({chunk.doc_id for chunk in self._chunks})
