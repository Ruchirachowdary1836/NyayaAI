from __future__ import annotations

import logging
import threading
from collections.abc import Callable
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
        # Background mode (embeddings API): the index is built by a worker thread and
        # requests never block on it; they get an explicit "building" error instead.
        self._background = False
        self._build_progress: tuple[int, int] | None = None
        self._dense_label = embedding_model
        self._dense_retrying = False
        self._stop = threading.Event()
        self._worker: threading.Thread | None = None
        self._document_count = len({chunk.doc_id for chunk in chunks})

    def get(self, name: str) -> Retriever:
        if name not in self._available_retrievers:
            raise ValueError(f"Unknown retriever {name!r}; choose bm25, dense, or hybrid")
        if name not in self._enabled_retrievers:
            raise RuntimeError(f"{name.title()} retrieval is disabled by deployment configuration.")
        if name in {"dense", "hybrid"} and self._dense is None:
            if self._background:
                raise RuntimeError(self._unavailable_message())
            self._load_dense()
        return self._retrievers[name]

    def _unavailable_message(self) -> str:
        if self._dense_error and not self._dense_retrying:
            return (
                f"Dense retrieval is unavailable: {self._dense_error} "
                "BM25 search remains available."
            )
        if self._build_progress:
            done, total = self._build_progress
            return (
                f"The dense index is still being built ({done:,} of {total:,} passages "
                "embedded). BM25 search is available now; try dense or hybrid later."
            )
        return "The dense index is being prepared. BM25 search is available now."

    def _install_dense(self, dense: DenseRetriever) -> None:
        _, alpha, method, rrf_k = self._dense_settings
        self._retrievers["dense"] = dense
        self._retrievers["hybrid"] = HybridRetriever(
            self._bm25, dense, method=method, alpha=alpha, rrf_k=rrf_k
        )
        self._dense = dense
        self._dense_error = None
        self._dense_retrying = False

    def mark_dense_unavailable(self, reason: str, label: str | None = None) -> None:
        """Report dense/hybrid as failed without attempting to load anything."""
        self._background = True
        self._dense_error = reason
        if label:
            self._dense_label = label

    def start_background_dense(
        self,
        build: Callable[[Callable[[int, int], None], threading.Event], DenseRetriever],
        label: str,
        retry_delay: float = 300.0,
        is_retryable: Callable[[Exception], bool] = lambda error: False,
    ) -> None:
        """Build the dense engine in a worker thread, retrying transient failures."""
        if not ({"dense", "hybrid"} & set(self._enabled_retrievers)) or not self._chunks:
            return
        self._background = True
        self._dense_label = label

        def progress(done: int, total: int) -> None:
            self._build_progress = (done, total)

        def run() -> None:
            while not self._stop.is_set():
                self._dense_loading = True
                try:
                    dense = build(progress, self._stop)
                except Exception as error:  # noqa: BLE001 - reported via status()
                    self._dense_loading = False
                    if self._stop.is_set():
                        return
                    self._dense_error = str(error)
                    self._dense_retrying = is_retryable(error)
                    logger.warning("Dense index build failed: %s", error)
                    if not self._dense_retrying:
                        return
                    self._stop.wait(retry_delay)
                    continue
                self._dense_loading = False
                self._install_dense(dense)
                logger.info("Dense index ready (%d passages)", len(self._chunks))
                return

        self._worker = threading.Thread(target=run, name="dense-index-builder", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=5)

    def _load_dense(self) -> None:
        with self._dense_lock:
            if self._dense is not None:
                return
            model = self._dense_settings[0]
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
            self._install_dense(dense)

    def warm(self) -> None:
        """Load the dense engine eagerly when it is enabled (used by deployments that opt in)."""
        if "dense" in self._enabled_retrievers or "hybrid" in self._enabled_retrievers:
            try:
                self._load_dense()
            except RuntimeError:
                pass

    def status(self) -> dict[str, dict[str, object]]:
        _, alpha, method, rrf_k = self._dense_settings
        model = self._dense_label
        statuses: dict[str, dict[str, object]] = {}
        for name in self._available_retrievers:
            if name not in self._enabled_retrievers:
                statuses[name] = {"state": "disabled"}
            elif name == "bm25":
                statuses[name] = {"state": "ready", "chunks": len(self._chunks)}
            elif self._dense is not None:
                statuses[name] = {"state": "ready", "model": model}
            elif self._dense_loading and self._background:
                done, total = self._build_progress or (0, len(self._chunks))
                statuses[name] = {
                    "state": "building",
                    "model": model,
                    "progress": {"embedded": done, "total": total},
                }
            elif self._dense_loading:
                statuses[name] = {"state": "loading", "model": model}
            elif self._dense_error:
                statuses[name] = {
                    "state": "failed",
                    "model": model,
                    "error": self._dense_error,
                    "retrying": self._dense_retrying,
                }
            elif self._background:
                statuses[name] = {"state": "building", "model": model}
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
    def chunks(self) -> list[LegalChunk]:
        return self._chunks

    @property
    def corpus_size(self) -> int:
        return len(self._chunks)

    @property
    def document_count(self) -> int:
        return self._document_count
