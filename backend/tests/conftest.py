from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from backend.app.core.config import settings
from backend.app.core.rate_limit import reset_all_limiters
from fastapi.testclient import TestClient

CORPUS = [
    {
        "doc_id": "C1",
        "source": "aila",
        "text": (
            "Ghana Pradhan v State of Orissa\nSupreme Court of India\n13 November 1990\n"
            "Cr.A. No. 716 of 1979\nThe appellant was convicted under Section 302 IPC for murder. "
            "The prosecution must prove intention to cause death beyond reasonable doubt."
        ),
        "metadata": {
            "title": "Ghana Pradhan v State of Orissa",
            "document_type": "judgment",
            "court": "Supreme Court of India",
            "judgment_date": "1990-11-13",
            "year": 1990,
            "case_number": "Cr.A. No. 716 of 1979",
        },
    },
    {
        "doc_id": "C2",
        "source": "aila",
        "text": (
            "Quashing of FIR\nSupreme Court of India\n8 July 2010\nCriminal Appeal No. 9 of 2010\n"
            "Section 482 CrPC preserves the inherent powers of the High Court to prevent abuse "
            "of the process of any court."
        ),
        "metadata": {
            "title": "Quashing of FIR",
            "document_type": "judgment",
            "court": "Supreme Court of India",
            "judgment_date": "2010-07-08",
            "year": 2010,
        },
    },
    {
        "doc_id": "S1",
        "source": "aila",
        "text": "Title: Punishment for murder\nWhoever commits murder shall be punished with death.",
        "metadata": {
            "title": "Punishment for murder",
            "document_type": "statute",
            "court": "Indian statute",
        },
    },
]


def write_corpus(directory: Path) -> tuple[Path, Path]:
    documents = directory / "documents.jsonl"
    chunks = directory / "chunks.jsonl"
    with (
        documents.open("w", encoding="utf-8") as doc_file,
        chunks.open("w", encoding="utf-8") as chunk_file,
    ):
        for record in CORPUS:
            doc_file.write(json.dumps(record) + "\n")
            chunk_file.write(
                json.dumps(
                    {
                        "doc_id": record["doc_id"],
                        "chunk_id": f"{record['doc_id']}:0",
                        "text": record["text"],
                        "start_char": 0,
                        "end_char": len(record["text"]),
                        "token_count": len(record["text"].split()),
                        "metadata": record["metadata"],
                    }
                )
                + "\n"
            )
    return documents, chunks


@pytest.fixture(autouse=True)
def isolate_runtime_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "data_chunks_path", str(tmp_path / "chunks.jsonl"))
    monkeypatch.setattr(settings, "data_documents_path", str(tmp_path / "documents.jsonl"))
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setattr(settings, "index_dir", str(tmp_path / "indices"))
    monkeypatch.setattr(settings, "results_dir", str(tmp_path / "results"))
    monkeypatch.setattr(settings, "enabled_retrievers", ["bm25"])
    monkeypatch.setattr(settings, "initial_admin_username", "")
    monkeypatch.setattr(settings, "initial_admin_password", "")
    reset_all_limiters()


class StubGenerator:
    """Deterministic generator used instead of a real model provider."""

    provider = "stub"
    model = "stub-model"
    configured = True

    def __init__(
        self, answer: str = "Murder under Section 302 IPC requires intention [1]."
    ) -> None:
        self.answer = answer
        self.error: Exception | None = None
        self.prompts: list[str] = []

    async def generate(self, prompt: str, seed: int = 42) -> str:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer

    async def stream(self, prompt: str, seed: int = 42):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        for token in self.answer.split(" "):
            yield token + " "


def wait_until_ready(client: TestClient) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        response = client.get("/ready")
        if response.status_code == 200:
            return
        time.sleep(0.02)
    raise AssertionError(f"Application did not become ready: {response.text}")


@pytest.fixture
def client(tmp_path) -> Iterator[TestClient]:
    from backend.app.main import app

    write_corpus(tmp_path)
    with TestClient(app) as test_client:
        wait_until_ready(test_client)
        app.state.generator = StubGenerator()
        yield test_client


def register(client: TestClient, username: str = "researcher", password: str = "long-password"):
    response = client.post(
        "/api/v1/auth/register", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_admin(client: TestClient, username: str = "chief", password: str = "admin-password-1"):
    from backend.app.services.auth import create_user

    database = client.app.state.database
    assert create_user(database, username, password, role="admin")
    response = client.post("/api/v1/auth/token", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
