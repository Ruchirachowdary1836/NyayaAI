from __future__ import annotations

import json
import threading
import time

import httpx
import numpy as np
import pytest
from backend.app.core.config import settings
from backend.app.db.database import Database
from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.dense import DenseRetriever
from backend.app.services.retrieval.embeddings import (
    EmbeddingAPIClient,
    EmbeddingError,
    EmbeddingIndexBuilder,
)
from backend.app.services.retrieval.registry import RetrieverRegistry
from conftest import register, wait_until_ready, write_corpus
from fastapi.testclient import TestClient

VOCABULARY = ["murder", "section", "fir", "court", "punished", "inherent", "death", "high"]


def bag_of_words(text: str, size: int = 12) -> list[float]:
    lowered = text.lower()
    vector = [float(lowered.count(word)) + 0.01 for word in VOCABULARY]
    return vector + [0.0] * (size - len(vector))


def fake_embeddings_api(calls: list[dict], size: int = 12):
    """An OpenAI-compatible /embeddings endpoint returning shuffled-order results."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append({"body": body, "auth": request.headers.get("authorization")})
        data = [
            {"index": index, "embedding": bag_of_words(text, size)}
            for index, text in enumerate(body["input"])
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    return httpx.MockTransport(handler)


def make_client(transport, **kwargs) -> EmbeddingAPIClient:
    return EmbeddingAPIClient(
        "https://embeddings.test/v1",
        "test-key",
        "test-embedding",
        requests_per_minute=0,
        transport=transport,
        sleep=lambda seconds: None,
        **kwargs,
    )


def chunks(count: int) -> list[LegalChunk]:
    texts = ["murder section", "fir high court", "inherent powers", "punished with death"]
    return [
        LegalChunk(f"D{i}", f"D{i}:0", texts[i % len(texts)] + f" {i}", 0, 10, 3)
        for i in range(count)
    ]


def test_client_orders_truncates_and_normalizes_vectors() -> None:
    calls: list[dict] = []
    client = make_client(fake_embeddings_api(calls), dimensions=4)
    vectors = client.embed(["murder murder", "fir"])
    assert vectors.shape == (2, 4)
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), 1.0, rtol=1e-5)
    assert vectors[0][0] > vectors[1][0]  # "murder" weight belongs to the first input
    assert calls[0]["auth"] == "Bearer test-key"
    assert calls[0]["body"] == {"model": "test-embedding", "input": ["murder murder", "fir"]}


def test_client_retries_rate_limits_and_fails_fast_on_bad_credentials() -> None:
    sleeps: list[float] = []
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "7"}),
            httpx.Response(503),
            httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0, 0.0]}]}),
        ]
    )
    client = EmbeddingAPIClient(
        "https://embeddings.test/v1",
        "k",
        "m",
        requests_per_minute=0,
        transport=httpx.MockTransport(lambda request: next(responses)),
        sleep=sleeps.append,
    )
    assert client.embed(["x"]).shape == (1, 2)
    assert sleeps == [7.0, 2.0]

    attempts = []

    def unauthorized(request):
        attempts.append(1)
        return httpx.Response(401)

    bad = make_client(httpx.MockTransport(unauthorized))
    with pytest.raises(EmbeddingError, match="credentials") as caught:
        bad.embed(["x"])
    assert caught.value.retryable is False
    assert len(attempts) == 1


@pytest.mark.parametrize(
    "payload",
    [{"data": [{"index": 0, "embedding": [1.0]}]}, {"unexpected": True}, "not-json"],
)
def test_client_rejects_malformed_responses(payload) -> None:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    client = make_client(httpx.MockTransport(lambda request: httpx.Response(200, text=content)))
    with pytest.raises(EmbeddingError):
        client.embed(["one", "two"])


def test_index_builds_in_batches_and_resumes_from_the_database(tmp_path) -> None:
    database = Database(f"sqlite:///{(tmp_path / 'emb.db').as_posix()}")
    database.initialize()
    corpus = chunks(7)
    calls: list[dict] = []
    failing = {"after": 1}

    def flaky(request: httpx.Request) -> httpx.Response:
        if len(calls) >= failing["after"]:
            return httpx.Response(401)
        return fake_embeddings_api(calls).handle_request(request)

    with pytest.raises(EmbeddingError):
        EmbeddingIndexBuilder(
            corpus, make_client(httpx.MockTransport(flaky)), database, batch_size=3
        ).build()
    assert len(calls) == 1  # The first batch was embedded and stored before the failure.

    resumed_calls: list[dict] = []
    progress: list[tuple[int, int]] = []
    builder = EmbeddingIndexBuilder(
        corpus, make_client(fake_embeddings_api(resumed_calls)), database, batch_size=3
    )
    matrix = builder.build(on_progress=lambda done, total: progress.append((done, total)))
    assert matrix.shape == (7, 12) and matrix.dtype == np.float16
    assert len(resumed_calls) == 2  # Only the two missing batches were requested.
    assert progress[0] == (3, 7) and progress[-1] == (7, 7)

    reuse_calls: list[dict] = []
    again = EmbeddingIndexBuilder(
        corpus, make_client(fake_embeddings_api(reuse_calls)), database, batch_size=3
    ).build()
    assert reuse_calls == []
    np.testing.assert_array_equal(again, matrix)

    # A changed corpus gets a new key; the old vectors are removed after it is built.
    changed = EmbeddingIndexBuilder(
        chunks(4), make_client(fake_embeddings_api([])), database, batch_size=3
    )
    changed.build()
    assert database.load_embedding_batches(builder.cache_key) == {}
    database.close()


def test_float16_precomputed_vectors_rank_like_float32() -> None:
    corpus = chunks(40)
    client = make_client(fake_embeddings_api([]))
    vectors = client.embed([chunk.text for chunk in corpus])
    exact = DenseRetriever(corpus, "m", encoder=client.encode_query, vectors=vectors)
    compact = DenseRetriever(
        corpus, "m", encoder=client.encode_query, vectors=vectors.astype(np.float16)
    )
    for query in ("murder", "high court fir", "punished with death"):
        assert [hit.doc_id for hit in exact.search(query, 5)] == [
            hit.doc_id for hit in compact.search(query, 5)
        ]


def test_registry_reports_background_build_progress_and_failures() -> None:
    corpus = chunks(5)
    release = threading.Event()
    registry = RetrieverRegistry(corpus, enabled_retrievers=["bm25", "dense", "hybrid"])
    client = make_client(fake_embeddings_api([]))

    def build(on_progress, stop):
        on_progress(2, 5)
        release.wait(5)
        vectors = client.embed([chunk.text for chunk in corpus])
        return DenseRetriever(corpus, "m", encoder=client.encode_query, vectors=vectors)

    registry.start_background_dense(build, "test-embedding")
    deadline = time.monotonic() + 2
    while registry.status()["dense"].get("progress") is None and time.monotonic() < deadline:
        time.sleep(0.01)
    status = registry.status()["dense"]
    assert status["state"] == "building"
    assert status["progress"] == {"embedded": 2, "total": 5}
    with pytest.raises(RuntimeError, match="2 of 5 passages"):
        registry.get("hybrid")
    assert registry.get("bm25").search("murder")
    release.set()
    deadline = time.monotonic() + 5
    while registry.status()["dense"]["state"] != "ready" and time.monotonic() < deadline:
        time.sleep(0.01)
    assert registry.get("hybrid").search("murder")
    registry.stop()

    failing = RetrieverRegistry(corpus, enabled_retrievers=["bm25", "dense"])

    def broken(on_progress, stop):
        raise EmbeddingError("Embedding API rejected the configured credentials.")

    failing.start_background_dense(broken, "test-embedding")
    failing._worker.join(2)
    assert failing.status()["dense"]["state"] == "failed"
    assert failing.status()["dense"]["retrying"] is False
    with pytest.raises(RuntimeError, match="rejected the configured credentials"):
        failing.get("dense")


@pytest.fixture
def api_embedding_settings(monkeypatch):
    monkeypatch.setattr(settings, "embedding_provider", "openai")
    monkeypatch.setattr(settings, "enabled_retrievers", ["bm25", "dense", "hybrid"])
    monkeypatch.setattr(settings, "embedding_model", "test-embedding")
    monkeypatch.setattr(settings, "embedding_api_base_url", "https://embeddings.test/v1")
    monkeypatch.setattr(settings, "embedding_batch_size", 2)
    monkeypatch.setattr(settings, "embedding_requests_per_minute", 0)


def _patch_client(monkeypatch, calls: list[dict]) -> None:
    from backend.app import main

    class FakeClient(EmbeddingAPIClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, transport=fake_embeddings_api(calls), **kwargs)

    monkeypatch.setattr(main, "EmbeddingAPIClient", FakeClient)


def _wait_for_dense(test_client, headers) -> dict:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        status = test_client.get("/ready").json()["retrievers"]["dense"]
        if status["state"] in {"ready", "failed"}:
            return status
        time.sleep(0.02)
    raise AssertionError(status)


def test_app_builds_api_embeddings_in_background_and_reuses_them(
    tmp_path, monkeypatch, api_embedding_settings
) -> None:
    from backend.app.main import app

    monkeypatch.setattr(settings, "embedding_api_key", "test-key")
    calls: list[dict] = []
    _patch_client(monkeypatch, calls)
    write_corpus(tmp_path)
    with TestClient(app) as test_client:
        wait_until_ready(test_client)
        headers = register(test_client)
        assert _wait_for_dense(test_client, headers)["state"] == "ready"
        dense = test_client.post(
            "/api/v1/search", headers=headers, json={"query": "murder", "retriever": "dense"}
        )
        assert dense.status_code == 200
        assert dense.json()["hits"][0]["doc_id"] in {"C1", "S1"}
        comparison = test_client.post(
            "/api/v1/compare", headers=headers, json={"query": "inherent powers High Court"}
        ).json()
        assert comparison["unavailable"] == {}
        assert set(comparison["results"]) == {"bm25", "dense", "hybrid"}
    # The 3-chunk corpus was embedded in batches of 2 before any query embeddings.
    assert [len(call["body"]["input"]) for call in calls[:2]] == [2, 1]

    restart_calls: list[dict] = []
    _patch_client(monkeypatch, restart_calls)
    with TestClient(app) as restarted:
        wait_until_ready(restarted)
        headers = {
            "Authorization": "Bearer "
            + restarted.post(
                "/api/v1/auth/token", json={"username": "researcher", "password": "long-password"}
            ).json()["access_token"]
        }
        assert _wait_for_dense(restarted, headers)["state"] == "ready"
    assert restart_calls == []  # Corpus vectors came from the database, not the API.


def test_app_reports_missing_embedding_key_without_breaking_bm25(
    tmp_path, monkeypatch, api_embedding_settings
) -> None:
    from backend.app.main import app

    monkeypatch.setattr(settings, "embedding_api_key", "")
    monkeypatch.setattr(settings, "generator_api_key", "")
    write_corpus(tmp_path)
    with TestClient(app) as test_client:
        wait_until_ready(test_client)
        headers = register(test_client)
        status = test_client.get("/ready").json()["retrievers"]["dense"]
        assert status["state"] == "failed"
        assert "EMBEDDING_API_KEY" in status["error"]
        dense = test_client.post(
            "/api/v1/search", headers=headers, json={"query": "murder", "retriever": "hybrid"}
        )
        assert dense.status_code == 503
        assert "EMBEDDING_API_KEY" in dense.json()["detail"]
        bm25 = test_client.post("/api/v1/search", headers=headers, json={"query": "murder"})
        assert bm25.status_code == 200
