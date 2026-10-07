from backend.app.db.database import _normalize_database_url


def test_normalize_postgres_urls_for_psycopg_v3():
    assert (
        _normalize_database_url("postgres://user:password@host:5432/database")
        == "postgresql+psycopg://user:password@host:5432/database"
    )
    assert (
        _normalize_database_url("postgresql://user:password@host:5432/database")
        == "postgresql+psycopg://user:password@host:5432/database"
    )


def test_preserve_explicit_driver_and_sqlite_urls():
    postgres_url = "postgresql+psycopg://user:password@host:5432/database"
    sqlite_url = "sqlite:///data/nyayaai.db"
    assert _normalize_database_url(postgres_url) == postgres_url
    assert _normalize_database_url(sqlite_url) == sqlite_url
