from __future__ import annotations

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Retriever
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever


class RetrieverRegistry:
    def __init__(
        self,
        chunks: list[LegalChunk],
        embedding_model: str = "BAAI/bge-m3",
        alpha: float = 0.7,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
    ) -> None:
        self._retrievers: dict[str, Retriever] = {}
        self._chunks = chunks
        self._bm25 = BM25Retriever(chunks)
        self._retrievers["bm25"] = self._bm25
        self._dense: DenseRetriever | None = None
        self._dense_settings = (embedding_model, alpha, fusion_method, rrf_k)

    def get(self, name: str) -> Retriever:
        if (name == "dense" or name == "hybrid") and self._dense is None:
            model, alpha, method, rrf_k = self._dense_settings
            self._dense = DenseRetriever(self._chunks, model_name=model)
            self._retrievers["dense"] = self._dense
            self._retrievers["hybrid"] = HybridRetriever(
                self._bm25, self._dense, method=method, alpha=alpha, rrf_k=rrf_k
            )
        try:
            return self._retrievers[name]
        except KeyError as error:
            raise ValueError(
                f"Unknown retriever {name!r}; choose bm25, dense, or hybrid"
            ) from error

    @property
    def available(self) -> list[str]:
        return ["bm25", "dense", "hybrid"]

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    @property
    def document_count(self) -> int:
        return len({chunk.doc_id for chunk in self._chunks})
