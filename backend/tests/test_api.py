from __future__ import annotations

import threading

import pytest
from backend.app.core.config import settings
from backend.app.main import app
from backend.app.services.generation.llm import GenerationError, OpenAICompatibleGenerator
from backend.app.services.retrieval.registry import RetrieverRegistry
from conftest import StubGenerator, register, wait_until_ready
from fastapi.testclient import TestClient


def test_health_ready_request_id_and_security_headers(client) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    ready = client.get("/ready").json()
    assert ready["status"] == "ready"
    assert ready["database"] == "ok"
    assert ready["corpus_documents"] == 3
    assert ready["retrievers"]["dense"] == {"state": "disabled"}
    response = client.get("/health", headers={"X-Request-ID": "trace-123"})
    assert response.headers["x-request-id"] == "trace-123"
    assert response.headers["x-content-type-options"] == "nosniff"
    unsafe = client.get("/health", headers={"X-Request-ID": "bad id\r\nInjected: 1"})
    assert unsafe.headers["x-request-id"] != "bad id\r\nInjected: 1"


def test_search_returns_metadata_excerpts_and_pagination(client) -> None:
    headers = register(client)
    response = client.post(
        "/api/v1/search", headers=headers, json={"query": "murder Section 302", "k": 1}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 2
    assert body["page"] == 1 and len(body["hits"]) == 1
    top = body["hits"][0]
    assert top["title"]
    assert "murder" in top["excerpt"].lower()
    second = client.post(
        "/api/v1/search", headers=headers, json={"query": "murder Section 302", "k": 1, "page": 2}
    ).json()
    assert second["hits"][0]["doc_id"] != top["doc_id"]


def test_search_filters_and_sorting(client) -> None:
    headers = register(client)
    statutes = client.post(
        "/api/v1/search", headers=headers, json={"query": "murder", "document_type": "statute"}
    ).json()
    assert [hit["doc_id"] for hit in statutes["hits"]] == ["S1"]
    dated = client.post(
        "/api/v1/search",
        headers=headers,
        json={"query": "Section court", "year_from": 2000, "year_to": 2020},
    ).json()
    assert {hit["doc_id"] for hit in dated["hits"]} == {"C2"}
    newest = client.post(
        "/api/v1/search", headers=headers, json={"query": "Supreme Court", "sort": "newest"}
    ).json()
    assert [hit["doc_id"] for hit in newest["hits"]][:2] == ["C2", "C1"]


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   "},
        {"query": ""},
        {"query": "x", "k": 0},
        {"query": "x", "k": 51},
        {"query": "x", "retriever": "magic"},
        {"query": "x", "year_from": 2015, "year_to": 2000},
        {"query": "x" * 2001},
    ],
)
def test_search_validation_errors(client, payload) -> None:
    headers = register(client)
    assert client.post("/api/v1/search", headers=headers, json=payload).status_code == 422


def test_no_results_and_disabled_engines_are_reported(client) -> None:
    headers = register(client)
    empty = client.post("/api/v1/search", headers=headers, json={"query": "quantum chromodynamics"})
    assert empty.status_code == 200
    assert empty.json()["hits"] == [] and empty.json()["corpus_available"] is True
    dense = client.post(
        "/api/v1/search", headers=headers, json={"query": "murder", "retriever": "dense"}
    )
    assert dense.status_code == 503
    assert "disabled by deployment configuration" in dense.json()["detail"]


def test_compare_reports_unavailable_engines_instead_of_substituting(client) -> None:
    headers = register(client)
    response = client.post(
        "/api/v1/compare",
        headers=headers,
        json={"query": "murder", "retrievers": ["bm25", "dense"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert list(body["results"]) == ["bm25"]
    assert "dense" in body["unavailable"]
    assert body["overlap"] == {}


def test_compare_with_dense_and_hybrid_using_injected_encoder(client) -> None:
    import numpy as np
    from backend.app.services.retrieval import registry as registry_module
    from backend.app.services.retrieval.dense import DenseRetriever

    vocabulary = ["murder", "section", "fir", "court", "punished"]

    def encode(texts):
        return np.array(
            [[text.lower().count(word) + 0.01 for word in vocabulary] for text in texts]
        )

    class EncodedDense(DenseRetriever):
        def __init__(self, chunks, model_name, **kwargs):
            super().__init__(chunks, model_name=model_name, encoder=encode, **kwargs)

    registry_module_dense = registry_module.DenseRetriever
    registry_module.DenseRetriever = EncodedDense
    try:
        app.state.retrievers = RetrieverRegistry(
            app.state.retrievers._chunks, enabled_retrievers=["bm25", "dense", "hybrid"]
        )
        headers = register(client)
        body = client.post(
            "/api/v1/compare", headers=headers, json={"query": "murder", "k": 3}
        ).json()
    finally:
        registry_module.DenseRetriever = registry_module_dense
    assert set(body["results"]) == {"bm25", "dense", "hybrid"}
    assert set(body["overlap"]) == {"bm25-dense", "bm25-hybrid", "dense-hybrid"}
    assert body["unavailable"] == {}
    hybrid_scores = body["results"]["hybrid"][0]["source_scores"]
    assert {"bm25_rank", "dense_rank", "fused"} <= set(hybrid_scores)


def test_qa_returns_cited_answer_with_linked_passages(client) -> None:
    headers = register(client)
    response = client.post("/api/v1/qa", headers=headers, json={"query": "murder Section 302 IPC"})
    assert response.status_code == 200
    body = response.json()
    assert body["refused"] is False
    assert body["citations"] == [1]
    assert body["passages"][0]["doc_id"] == "C1"
    assert body["passages"][0]["title"] == "Ghana Pradhan v State of Orissa"
    assert "not legal advice" in body["disclaimer"]
    assert body["model"] == "stub-model"
    # Passages are labelled with their source in the prompt.
    assert "Source: Ghana Pradhan v State of Orissa" in app.state.generator.prompts[0]


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("This is supported [7].", "invalid_citations"),
        ("Murder is always punished with death.", "uncited_answer"),
        (
            "The available evidence is insufficient to answer this question.",
            "insufficient_evidence",
        ),
    ],
)
def test_qa_withholds_ungrounded_answers(client, answer, reason) -> None:
    headers = register(client)
    app.state.generator = StubGenerator(answer)
    body = client.post("/api/v1/qa", headers=headers, json={"query": "murder"}).json()
    assert body["refused"] is True
    assert body["refusal_reason"] == reason
    if reason != "insufficient_evidence":
        assert answer not in body["answer"]
    assert body["passages"]


def test_qa_separates_interpretation_from_sourced_text(client) -> None:
    headers = register(client)
    app.state.generator = StubGenerator(
        "Intention must be proved [1].\n\nInterpretation: Courts weigh circumstantial evidence."
    )
    body = client.post("/api/v1/qa", headers=headers, json={"query": "murder intention"}).json()
    assert body["refused"] is False
    assert body["interpretation"] == "Courts weigh circumstantial evidence."
    assert body["unsupported_sentences"] == []


def test_qa_refuses_without_evidence_and_without_provider(client) -> None:
    headers = register(client)
    refusal = client.post("/api/v1/qa", headers=headers, json={"query": "quantum chromodynamics"})
    assert refusal.json()["refused"] is True
    assert refusal.json()["refusal_reason"] == "no_evidence"
    app.state.generator = OpenAICompatibleGenerator("", model="gpt-4o-mini")
    unconfigured = client.post("/api/v1/qa", headers=headers, json={"query": "murder"})
    assert unconfigured.status_code == 503
    assert "GENERATOR_API_KEY" in unconfigured.json()["detail"]
    # Retrieval keeps working when generation is not configured.
    assert (
        client.post("/api/v1/search", headers=headers, json={"query": "murder"}).status_code == 200
    )


@pytest.mark.parametrize(("status", "kind"), [(504, "timeout"), (503, "auth"), (502, "malformed")])
def test_qa_maps_provider_failures_to_explicit_errors(client, status, kind) -> None:
    headers = register(client)
    generator = StubGenerator()
    generator.error = GenerationError(f"provider failed ({kind})", status, kind)
    app.state.generator = generator
    response = client.post("/api/v1/qa", headers=headers, json={"query": "murder"})
    assert response.status_code == status
    assert response.json()["detail"] == f"provider failed ({kind})"


def test_qa_stream_uses_post_body_and_emits_audited_completion(client) -> None:
    headers = register(client)
    response = client.post(
        "/api/v1/qa/stream", headers=headers, json={"query": "murder Section 302"}
    )
    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: complete" in response.text
    assert '"citations": [1]' in response.text
    generator = StubGenerator()
    generator.error = GenerationError("provider timed out", 504, "timeout")
    app.state.generator = generator
    failed = client.post("/api/v1/qa/stream", headers=headers, json={"query": "murder"})
    assert "event: error" in failed.text and "provider timed out" in failed.text


def test_qa_is_rate_limited_per_user(client, monkeypatch) -> None:
    monkeypatch.setattr(settings, "qa_rate_limit_per_minute", 2)
    headers = register(client)
    statuses = [
        client.post("/api/v1/qa", headers=headers, json={"query": "murder"}).status_code
        for _ in range(3)
    ]
    assert statuses == [200, 200, 429]


def test_corpus_documents_listing_and_viewer(client) -> None:
    headers = register(client)
    listing = client.get("/api/v1/documents", headers=headers, params={"document_type": "judgment"})
    assert listing.status_code == 200
    assert listing.json()["total"] == 2
    assert listing.json()["facets"]["document_types"] == ["judgment", "statute"]
    filtered = client.get("/api/v1/documents", headers=headers, params={"q": "quashing"}).json()
    assert [document["doc_id"] for document in filtered["documents"]] == ["C2"]
    document = client.get("/api/v1/documents/C1", headers=headers).json()
    assert document["document"]["metadata"]["case_number"] == "Cr.A. No. 716 of 1979"
    assert document["chunks"][0]["chunk_id"] == "C1:0"
    assert client.get("/api/v1/documents/missing", headers=headers).status_code == 404
    assert (
        client.get("/api/v1/documents", headers=headers, params={"limit": 500}).status_code == 422
    )


def test_feedback_is_recorded(client) -> None:
    headers = register(client)
    response = client.post(
        "/api/v1/feedback",
        headers=headers,
        json={"query": "murder", "rating": "up", "correctness": 5},
    )
    assert response.status_code == 201
    assert client.app.state.database.count_feedback() == {"up": 1}
    assert (
        client.post(
            "/api/v1/feedback", headers=headers, json={"query": "murder", "rating": "meh"}
        ).status_code
        == 422
    )


def test_dashboard_reflects_real_activity(client) -> None:
    headers = register(client)
    client.post("/api/v1/search", headers=headers, json={"query": "murder"})
    body = client.get("/api/v1/dashboard", headers=headers).json()
    assert body["user"]["username"] == "researcher"
    assert body["corpus"]["documents"] == 3
    assert body["activity_last_30_days"]["search"] == 1
    assert body["library"]["total"] == 0


def test_liveness_is_available_while_runtime_initializes(monkeypatch) -> None:
    from backend.app import main

    started = threading.Event()
    release = threading.Event()
    original = main._initialize_runtime

    def slow_initialize(application) -> None:
        started.set()
        if not release.wait(timeout=5):
            raise TimeoutError("Test initialization was not released")
        original(application)

    monkeypatch.setattr(main, "_initialize_runtime", slow_initialize)
    try:
        with TestClient(app) as test_client:
            assert started.wait(timeout=2)
            assert test_client.get("/health").json() == {"status": "ok"}
            assert test_client.get("/ready").status_code == 503
            preflight = test_client.options(
                "/api/v1/search",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
            busy = test_client.post("/api/v1/search", json={"query": "Section 482"})
            assert busy.status_code == 503
            assert busy.json()["status"] == "initializing"
            release.set()
            wait_until_ready(test_client)
    finally:
        release.set()


def test_initialization_failure_is_reported_without_exposing_details(monkeypatch) -> None:
    from backend.app import main

    def fail_initialize(application) -> None:
        raise RuntimeError("database password must not be exposed")

    monkeypatch.setattr(main, "_initialize_runtime", fail_initialize)
    import time

    with TestClient(app) as test_client:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            response = test_client.get("/ready")
            if response.json()["status"] == "failed":
                break
            time.sleep(0.02)
        assert response.status_code == 503
        assert "password" not in response.json()["detail"]
        assert test_client.post("/api/v1/search", json={"query": "x"}).json()["status"] == "failed"


def test_production_startup_rejects_unsafe_configuration(monkeypatch) -> None:
    from backend.app import main

    from backend.app.core.config import DEFAULT_JWT_SECRET

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jwt_secret_key", DEFAULT_JWT_SECRET)
    with pytest.raises(RuntimeError, match="JWT_SECRET_KEY"):
        main._initialize_runtime(app)
    monkeypatch.setattr(settings, "jwt_secret_key", "x" * 40)
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pw@db/nyaya")
    with pytest.raises(RuntimeError, match="non-empty processed chunk index"):
        main._initialize_runtime(app)
