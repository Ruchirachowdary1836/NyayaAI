import sqlite3

from backend.app.db.database import Database, normalize_database_url
from sqlalchemy import inspect


def test_normalize_postgres_urls_for_psycopg_v3():
    assert (
        normalize_database_url("postgres://user:password@host:5432/database")
        == "postgresql+psycopg://user:password@host:5432/database"
    )
    assert (
        normalize_database_url("postgresql://user:password@host:5432/database")
        == "postgresql+psycopg://user:password@host:5432/database"
    )


def test_preserve_explicit_driver_and_sqlite_urls():
    postgres_url = "postgresql+psycopg://user:password@host:5432/database"
    sqlite_url = "sqlite:///data/nyayaai.db"
    assert normalize_database_url(postgres_url) == postgres_url
    assert normalize_database_url(sqlite_url) == sqlite_url


def test_migrations_create_schema_and_are_idempotent(tmp_path):
    database = Database(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    database.initialize()
    database.initialize()
    assert database.schema_revision() == "0003_embedding_batches"
    tables = set(inspect(database.engine).get_table_names())
    assert {
        "users",
        "feedback",
        "revoked_tokens",
        "user_documents",
        "experiments",
        "usage_events",
    } <= tables
    database.close()


def test_migrations_adopt_a_pre_migration_database_without_data_loss(tmp_path):
    path = tmp_path / "legacy.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE users (username VARCHAR(80) PRIMARY KEY, password_hash BLOB NOT NULL,
          password_salt BLOB NOT NULL, role VARCHAR(8) NOT NULL,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL);
        INSERT INTO users (username, password_hash, password_salt, role) VALUES ('legacy', x'00', x'00', 'admin');
        CREATE TABLE feedback (feedback_id VARCHAR(36) PRIMARY KEY, query TEXT NOT NULL,
          rating VARCHAR(4) NOT NULL, correctness INTEGER, comment TEXT,
          created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL);
        INSERT INTO feedback (feedback_id, query, rating) VALUES ('f1', 'q', 'up');
        """
    )
    connection.commit()
    connection.close()
    database = Database(f"sqlite:///{path.as_posix()}")
    database.initialize()
    profile = database.get_user_profile("legacy")
    assert profile is not None and profile["role"] == "admin" and profile["is_active"] is True
    assert database.count_feedback() == {"up": 1}
    database.close()


def test_deleting_a_user_cascades_to_their_documents(tmp_path):
    from sqlalchemy import delete

    from backend.app.db.tables import users

    database = Database(f"sqlite:///{(tmp_path / 'cascade.db').as_posix()}")
    database.initialize()
    database.create_user("owner", b"h", b"s", "user")
    database.insert_user_document(
        {
            "document_id": "d1",
            "owner": "owner",
            "title": "t",
            "filename": "f.txt",
            "content_type": "text/plain",
            "size_bytes": 1,
            "sha256": "x",
            "status": "ready",
            "error": None,
            "text": "t",
            "page_count": None,
            "char_count": 1,
            "content": b"t",
        }
    )
    assert database.update_user_credentials("owner", "renamed")
    assert database.get_user_document("renamed", "d1") is not None
    with database.engine.begin() as connection:
        connection.execute(delete(users).where(users.c.username == "renamed"))
    assert database.count_user_documents() == {}
    database.close()
