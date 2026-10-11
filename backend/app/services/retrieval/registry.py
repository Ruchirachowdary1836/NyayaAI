from __future__ import annotations

import logging
import threading
from pathlib import Path

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.base import Retriever
from backend.app.services.retrieval.bm25 import BM25Retriever
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.hybrid import HybridRetriever

logger = logging.getLogger("nyayaai.retrieval")


class RetrieverRegistry:
    """Owns the corpus chunks and the retrieval engines enabled for this deployment.

    BM25 is built eagerly. The dense model and its index are loaded on first use of
    ``dense`` or ``hybrid``; a failure is recorded and reported, never replaced by a
    silent BM25 fallback.
    """

    _available_retrievers = ("bm25", "dense", "hybrid")

    def __init__(
        self,
        chunks: list[LegalChunk],
        embedding_model: str = "BAAI/bge-m3",
        alpha: float = 0.7,
        fusion_method: str = "rrf",
        rrf_k: int = 60,
        enabled_retrievers: list[str] | None = None,
        embedding_cache_dir: str | Path | None = None,
    ) -> None:
        enabled = (
            list(self._available_retrievers) if enabled_retrievers is None else enabled_retrievers
        )
        unknown = set(enabled) - set(self._available_retrievers)
        if unknown:
            raise ValueError(f"Unknown retrievers configured: {', '.join(sorted(unknown))}")
        if "bm25" not in enabled and enabled:
            logger.info("BM25 is always available; it is required by hybrid retrieval")
        self._retrievers: dict[str, Retriever] = {}
        self._chunks = chunks
        self._bm25 = BM25Retriever(chunks)
        self._retrievers["bm25"] = self._bm25
        self._enabled_retrievers = tuple(
            name for name in self._available_retrievers if name in enabled or name == "bm25"
        )
        self._dense: DenseRetriever | None = None
        self._dense_lock = threading.Lock()
        self._dense_error: str | None = None
        self._dense_loading = False
        self._dense_settings = (embedding_model, alpha, fusion_method, rrf_k)
        self._embedding_cache_dir = embedding_cache_dir
        self._chunks_by_doc: dict[str, list[LegalChunk]] | None = None
        self._document_count = len({chunk.doc_id for chunk in chunks})

    def get(self, name: str) -> Retriever:
        if name not in self._available_retrievers:
            raise ValueError(f"Unknown retriever {name!r}; choose bm25, dense, or hybrid")
        if name not in self._enabled_retrievers:
            raise RuntimeError(f"{name.title()} retrieval is disabled by deployment configuration.")
        if name in {"dense", "hybrid"} and self._dense is None:
            self._load_dense()
        return self._retrievers[name]

    def _load_dense(self) -> None:
        with self._dense_lock:
            if self._dense is not None:
                return
            model, alpha, method, rrf_k = self._dense_settings
            self._dense_loading = True
            try:
                kwargs = (
                    {"cache_dir": self._embedding_cache_dir} if self._embedding_cache_dir else {}
                )
                dense = DenseRetriever(self._chunks, model_name=model, **kwargs)
            except Exception as error:
                self._dense_error = f"{type(error).__name__}: {error}"
                logger.exception("Dense retriever failed to load model=%s", model)
                raise RuntimeError(
                    f"Dense retrieval is unavailable: the embedding model {model!r} could not be "
                    "loaded on this server. BM25 search remains available."
                ) from error
            finally:
                self._dense_loading = False
            self._retrievers["dense"] = dense
            self._retrievers["hybrid"] = HybridRetriever(
                self._bm25, dense, method=method, alpha=alpha, rrf_k=rrf_k
            )
            self._dense = dense
            self._dense_error = None

    def warm(self) -> None:
        """Load the dense engine eagerly when it is enabled (used by deployments that opt in)."""
        if "dense" in self._enabled_retrievers or "hybrid" in self._enabled_retrievers:
            try:
                self._load_dense()
            except RuntimeError:
                pass

    def status(self) -> dict[str, dict[str, object]]:
        model, alpha, method, rrf_k = self._dense_settings
        statuses: dict[str, dict[str, object]] = {}
        for name in self._available_retrievers:
            if name not in self._enabled_retrievers:
                statuses[name] = {"state": "disabled"}
            elif name == "bm25":
                statuses[name] = {"state": "ready", "chunks": len(self._chunks)}
            elif self._dense is not None:
                statuses[name] = {"state": "ready", "model": model}
            elif self._dense_loading:
                statuses[name] = {"state": "loading", "model": model}
            elif self._dense_error:
                statuses[name] = {"state": "failed", "model": model, "error": self._dense_error}
            else:
                statuses[name] = {"state": "not_loaded", "model": model}
            if name == "hybrid" and name in self._enabled_retrievers:
                statuses[name].update({"fusion": method, "alpha": alpha, "rrf_k": rrf_k})
        return statuses

    def chunks_for(self, doc_id: str) -> list[LegalChunk]:
        if self._chunks_by_doc is None:
            grouped: dict[str, list[LegalChunk]] = {}
            for chunk in self._chunks:
                grouped.setdefault(chunk.doc_id, []).append(chunk)
            self._chunks_by_doc = grouped
        return self._chunks_by_doc.get(doc_id, [])

    @property
    def available(self) -> list[str]:
        return list(self._enabled_retrievers)

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    @property
    def document_count(self) -> int:
        return self._document_count
