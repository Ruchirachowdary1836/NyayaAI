"""Repository tests against a real PostgreSQL server.

Skipped unless NYAYAAI_TEST_POSTGRES_URL points to a disposable test database
(CI starts one). Never point this at a database containing real data.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from backend.app.db.database import Database, DuplicateRecordError

POSTGRES_URL = os.getenv("NYAYAAI_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="NYAYAAI_TEST_POSTGRES_URL not set")


@pytest.fixture
def database():
    db = Database(POSTGRES_URL or "")
    db.initialize()
    yield db
    db.close()


def test_postgres_schema_and_repository_operations(database) -> None:
    assert database.schema_revision() == "0002_platform_tables"
    owner = f"pg_{uuid.uuid4().hex[:8]}"
    assert database.create_user(owner, b"hash", b"salt", "user")
    assert database.get_user_role(owner) == "user"

    record = {
        "document_id": str(uuid.uuid4()),
        "owner": owner,
        "title": "Brief",
        "filename": "brief.txt",
        "content_type": "text/plain",
        "size_bytes": 5,
        "sha256": uuid.uuid4().hex,
        "status": "ready",
        "error": None,
        "text": "brief",
        "page_count": None,
        "char_count": 5,
        "content": b"brief",
    }
    database.insert_user_document(record)
    with pytest.raises(DuplicateRecordError):
        database.insert_user_document({**record, "document_id": str(uuid.uuid4())})
    documents, total = database.list_user_documents(owner, query="BRI")
    assert total == 1 and documents[0]["title"] == "Brief"
    assert (
        database.get_user_document(owner, record["document_id"], include_content=True)["content"]
        == b"brief"
    )

    database.insert_experiment(
        {
            "experiment_id": str(uuid.uuid4()),
            "owner": owner,
            "name": "pg",
            "status": "completed",
            "config": {"k": 5},
            "results": {"queries": []},
            "summary": {"systems": {}},
            "duration_ms": 1.0,
        }
    )
    experiments, count = database.list_experiments(owner)
    assert count == 1 and experiments[0]["config"] == {"k": 5}

    database.record_usage(owner, "search", "ok", retriever="bm25", latency_ms=2.0)
    summary = database.usage_summary(datetime.now(UTC) - timedelta(minutes=5), username=owner)
    assert summary[0]["count"] == 1

    jti = uuid.uuid4().hex
    database.revoke_token(jti, owner, datetime.now(UTC) + timedelta(hours=1))
    database.revoke_token(jti, owner, datetime.now(UTC) + timedelta(hours=1))
    assert database.is_token_revoked(jti)

    # Renaming cascades to owned rows.
    renamed = owner + "_r"
    assert database.update_user_credentials(owner, renamed)
    assert database.list_user_documents(renamed)[1] == 1
