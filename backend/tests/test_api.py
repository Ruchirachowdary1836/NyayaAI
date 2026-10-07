from __future__ import annotations

import json
from pathlib import Path

from backend.app.api.v1.feedback import initialize_feedback_store
from backend.app.core.security import create_access_token
from backend.app.main import app
from backend.app.services.auth import create_user, initialize_auth_store
from backend.app.services.ingestion.chunker import LegalChunk
from backend.app.services.retrieval.registry import RetrieverRegistry
from fastapi.testclient import TestClient


def test_search_qa_document_feedback_and_request_id(tmp_path: Path) -> None:
    with TestClient(app) as client:
        text = "Section 482 CrPC permits the High Court to exercise inherent powers."
        app.state.retrievers = RetrieverRegistry(
            [LegalChunk("case-1", "case-1:0", text, 0, len(text), len(text.split()))]
        )
        app.state.documents_path = tmp_path / "documents.jsonl"
        app.state.documents_path.write_text(
            json.dumps({"doc_id": "case-1", "text": text, "source": "test", "metadata": {}}) + "\n",
            encoding="utf-8",
        )
        app.state.feedback_db = tmp_path / "feedback.db"
        initialize_feedback_store(app.state.feedback_db)
        app.state.results_dir = tmp_path / "results"
        search_response = client.post(
            "/api/v1/search",
            json={"query": "Section 482 CrPC", "retriever": "bm25", "k": 5},
            headers={"X-Request-ID": "test-request"},
        )
        assert search_response.status_code == 200
        assert search_response.headers["x-request-id"] == "test-request"
        assert search_response.json()["hits"][0]["doc_id"] == "case-1"

        refusal = client.post(
            "/api/v1/qa",
            json={"query": "quantum mechanics", "retriever": "bm25", "k": 5},
        )
        assert refusal.status_code == 200
        assert refusal.json()["refused"] is True
        assert "not legal advice" in refusal.json()["disclaimer"]

        document = client.get("/api/v1/documents/case-1")
        assert document.status_code == 200
        assert document.json()["document"]["doc_id"] == "case-1"
        assert client.get("/api/v1/documents/missing").status_code == 404

        feedback = client.post(
            "/api/v1/feedback",
            json={"query": "Section 482", "rating": "up", "correctness": 5},
        )
        assert feedback.status_code == 201
        assert feedback.json()["accepted"] is True

        ready = client.get("/ready")
        assert ready.json()["corpus_documents"] == 1
        assert ready.json()["corpus_chunks"] == 1


def test_compare_has_overlap_statistics(tmp_path: Path) -> None:
    with TestClient(app) as client:
        app.state.retrievers = RetrieverRegistry([])
        app.state.documents_path = tmp_path / "documents.jsonl"
        app.state.feedback_db = tmp_path / "feedback.db"
        app.state.results_dir = tmp_path / "results"
        response = client.post(
            "/api/v1/compare",
            json={"query": "Section 482", "retriever": "bm25", "k": 3},
        )

    assert response.status_code == 200
    assert response.json()["results"] == {"bm25": [], "dense": [], "hybrid": []}
    assert all(value == 0 for value in response.json()["overlap"].values())


def test_registration_login_and_admin_role_enforcement(tmp_path: Path) -> None:
    with TestClient(app) as client:
        auth_path = tmp_path / "auth.db"
        initialize_auth_store(auth_path)
        app.state.auth_db = auth_path
        registration = client.post(
            "/api/v1/auth/register",
            json={"username": "researcher", "password": "long-password"},
        )
        assert registration.status_code == 201
        token = registration.json()["access_token"]
        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        ).json() == {"username": "researcher", "role": "user"}
        assert (
            client.get(
                "/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}
            ).status_code
            == 403
        )

        login = client.post(
            "/api/v1/auth/token",
            json={"username": "researcher", "password": "long-password"},
        )
        assert login.status_code == 200
        assert create_user(auth_path, "administrator", "long-password", role="admin")
        admin_token = create_access_token("administrator", role="admin")
        users = client.get(
            "/api/v1/admin/users", headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert users.status_code == 200
        assert {user["role"] for user in users.json()} == {"user", "admin"}


def test_user_can_edit_profile_and_old_token_is_revoked(tmp_path: Path) -> None:
    with TestClient(app) as client:
        auth_path = tmp_path / "profile.db"
        initialize_auth_store(auth_path)
        app.state.auth_db = auth_path
        registration = client.post(
            "/api/v1/auth/register",
            json={"username": "researcher", "password": "long-password"},
        )
        old_token = registration.json()["access_token"]
        response = client.put(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {old_token}"},
            json={
                "current_password": "long-password",
                "username": "legal-researcher",
                "new_password": "new-long-password",
            },
        )
        assert response.status_code == 200
        new_token = response.json()["access_token"]
        assert client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"}
        ).json() == {"username": "legal-researcher", "role": "user"}
        assert (
            client.get(
                "/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"}
            ).status_code
            == 401
        )
        login = client.post(
            "/api/v1/auth/token",
            json={"username": "legal-researcher", "password": "new-long-password"},
        )
        assert login.status_code == 200
        wrong_password = client.put(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {new_token}"},
            json={"current_password": "wrong-password", "username": "legal-researcher"},
        )
        assert wrong_password.status_code == 401


def test_qa_stream_emits_tokens_and_audited_completion(tmp_path: Path) -> None:
    class Generator:
        async def stream(self, prompt: str):
            yield "A supported statement "
            yield "[1]."

    with TestClient(app) as client:
        text = "Section 482 CrPC permits the High Court to exercise inherent powers."
        app.state.retrievers = RetrieverRegistry(
            [LegalChunk("case-1", "case-1:0", text, 0, len(text), len(text.split()))]
        )
        app.state.generator = Generator()
        response = client.get("/api/v1/qa/stream?query=Section%20482%20CrPC&retriever=bm25")

    assert response.status_code == 200
    assert "event: token" in response.text
    assert "event: complete" in response.text
    assert '"citations": [1]' in response.text
    assert (
        '"disclaimer": "For informational purposes only; this is not legal advice."'
        in response.text
    )


def test_qa_does_not_fabricate_answer_when_provider_key_is_missing() -> None:
    from backend.app.services.generation.llm import OpenAICompatibleGenerator

    with TestClient(app) as client:
        text = "Section 482 CrPC permits the High Court to exercise inherent powers."
        app.state.retrievers = RetrieverRegistry(
            [LegalChunk("case-1", "case-1:0", text, 0, len(text), len(text.split()))]
        )
        app.state.generator = OpenAICompatibleGenerator(
            "", model="gpt-4o-mini", base_url="https://api.openai.com/v1"
        )
        response = client.post(
            "/api/v1/qa",
            json={"query": "Section 482 CrPC", "retriever": "bm25", "k": 5},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "AI answer generation is not configured. Set GENERATOR_API_KEY in the API service."
    )
