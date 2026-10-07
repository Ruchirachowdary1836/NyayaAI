from __future__ import annotations

import pytest
from backend.app.core.config import settings


@pytest.fixture(autouse=True)
def isolate_runtime_data(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "data_chunks_path", str(tmp_path / "chunks.jsonl"))
    monkeypatch.setattr(settings, "data_documents_path", str(tmp_path / "documents.jsonl"))
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'nyayaai-test.db'}")
