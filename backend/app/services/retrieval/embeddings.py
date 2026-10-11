"""Dense embeddings from an OpenAI-compatible ``/embeddings`` API (e.g. Gemini).

Used when the API host cannot run a local sentence-transformer (no PyTorch, small RAM).
Corpus vectors are computed once in batches, stored in the database, and reused across
restarts; only queries are embedded at search time.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections.abc import Callable, Sequence
from typing import Protocol

import httpx
import numpy as np

from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.dense import corpus_fingerprint

logger = logging.getLogger("nyayaai.embeddings")

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}
STORED_DTYPE = np.float16


class EmbeddingError(RuntimeError):
    """An embeddings API failure. ``retryable`` marks transient conditions."""

    def __init__(self, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class BuildCancelled(Exception):
    """The background index build was stopped (application shutdown)."""


def truncate_and_normalize(vectors: np.ndarray, dimensions: int | None) -> np.ndarray:
    vectors = np.asarray(vectors, dtype=np.float32)
    if dimensions is not None and vectors.shape[1] > dimensions:
        # Valid for Matryoshka-trained models such as gemini-embedding-001.
        vectors = vectors[:, :dimensions]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors / np.maximum(norms, 1e-12)


class EmbeddingAPIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        requests_per_minute: int = 60,
        timeout: float = 60.0,
        max_retries: int = 5,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model
        self.dimensions = dimensions
        self.min_interval = 60.0 / requests_per_minute if requests_per_minute > 0 else 0.0
        self.timeout = timeout
        self.max_retries = max_retries
        self._transport = transport
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_request = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def _throttle(self) -> None:
        with self._lock:
            wait = self._last_request + self.min_interval - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()

    def embed(self, texts: Sequence[str], throttle: bool = True) -> np.ndarray:
        if not self.api_key:
            raise EmbeddingError("Embedding API key is not configured (EMBEDDING_API_KEY).")
        payload = {"model": self.model, "input": list(texts)}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        last_error: EmbeddingError | None = None
        for attempt in range(self.max_retries + 1):
            if throttle:
                self._throttle()
            try:
                with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                    response = client.post(
                        f"{self.base_url}/embeddings", json=payload, headers=headers
                    )
            except httpx.TimeoutException:
                last_error = EmbeddingError("Embedding API request timed out.", retryable=True)
            except httpx.HTTPError:
                last_error = EmbeddingError("Embedding API is unreachable.", retryable=True)
            else:
                if response.status_code < 400:
                    return self._parse(response, len(texts))
                last_error = self._status_error(response.status_code)
                if not last_error.retryable:
                    raise last_error
                retry_after = response.headers.get("retry-after", "")
                if retry_after.isdigit() and attempt < self.max_retries:
                    self._sleep(min(float(retry_after), 120.0))
                    continue
            if attempt < self.max_retries:
                self._sleep(min(2.0**attempt, 60.0))
        assert last_error is not None
        raise last_error

    @staticmethod
    def _status_error(status: int) -> EmbeddingError:
        if status in {401, 403}:
            return EmbeddingError(
                "Embedding API rejected the configured credentials; check EMBEDDING_API_KEY "
                "(or GENERATOR_API_KEY)."
            )
        if status == 404:
            return EmbeddingError(
                "Embedding API does not recognise the configured model; check EMBEDDING_MODEL."
            )
        if status == 429:
            return EmbeddingError("Embedding API rate limit or quota exceeded.", retryable=True)
        return EmbeddingError(
            f"Embedding API returned HTTP {status}.", retryable=status in _RETRYABLE_STATUS
        )

    def _parse(self, response: httpx.Response, expected: int) -> np.ndarray:
        try:
            data = response.json()["data"]
            ordered = sorted(data, key=lambda item: item.get("index", 0))
            vectors = np.array([item["embedding"] for item in ordered], dtype=np.float32)
        except (ValueError, KeyError, TypeError) as error:
            raise EmbeddingError("Embedding API returned a malformed response.") from error
        if vectors.ndim != 2 or len(vectors) != expected:
            raise EmbeddingError(
                f"Embedding API returned {len(vectors)} vectors for {expected} inputs."
            )
        return truncate_and_normalize(vectors, self.dimensions)

    def encode_query(self, texts: list[str]) -> np.ndarray:
        # Interactive queries are not throttled; the corpus build is.
        return self.embed(texts, throttle=False)


class EmbeddingStore(Protocol):
    def save_embedding_batch(
        self, cache_key: str, batch_index: int, row_count: int, dimensions: int, vectors: bytes
    ) -> None: ...

    def load_embedding_batches(self, cache_key: str) -> dict[int, tuple[int, int, bytes]]: ...

    def delete_stale_embeddings(self, keep_cache_key: str) -> int: ...


class EmbeddingIndexBuilder:
    """Embeds the corpus in batches, persisting each batch so builds resume after restarts."""

    def __init__(
        self,
        chunks: list[LegalChunk],
        client: EmbeddingAPIClient,
        store: EmbeddingStore,
        batch_size: int = 50,
    ) -> None:
        self.chunks = chunks
        self.client = client
        self.store = store
        self.batch_size = max(1, batch_size)
        label = f"api:{client.base_url}:{client.model}:{client.dimensions}:{self.batch_size}"
        self.cache_key = corpus_fingerprint(label, chunks)

    @property
    def batch_count(self) -> int:
        return math.ceil(len(self.chunks) / self.batch_size)

    def build(
        self,
        on_progress: Callable[[int, int], None] | None = None,
        stop: threading.Event | None = None,
    ) -> np.ndarray:
        total = len(self.chunks)
        existing = self.store.load_embedding_batches(self.cache_key)
        batches: dict[int, np.ndarray] = {}
        done = 0
        for index in range(self.batch_count):
            start = index * self.batch_size
            rows = min(self.batch_size, total - start)
            cached = existing.get(index)
            if cached and cached[0] == rows:
                row_count, dimensions, blob = cached
                batches[index] = np.frombuffer(blob, dtype=STORED_DTYPE).reshape(
                    row_count, dimensions
                )
                done += rows
        if on_progress:
            on_progress(done, total)
        if done:
            logger.info("Reusing %d stored embeddings (key %s)", done, self.cache_key[:12])
        for index in range(self.batch_count):
            if index in batches:
                continue
            if stop is not None and stop.is_set():
                raise BuildCancelled()
            start = index * self.batch_size
            texts = [chunk.text for chunk in self.chunks[start : start + self.batch_size]]
            vectors = self.client.embed(texts).astype(STORED_DTYPE)
            self.store.save_embedding_batch(
                self.cache_key, index, len(texts), vectors.shape[1], vectors.tobytes()
            )
            batches[index] = vectors
            done += len(texts)
            if on_progress:
                on_progress(done, total)
        matrix = np.concatenate([batches[index] for index in range(self.batch_count)])
        removed = self.store.delete_stale_embeddings(self.cache_key)
        if removed:
            logger.info("Removed %d stale embedding batches", removed)
        return matrix
