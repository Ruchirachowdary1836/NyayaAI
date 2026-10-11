from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine

from backend.app.db.tables import metadata

config = context.config
target_metadata = metadata


def _database_url() -> str:
    from backend.app.core.config import settings
    from backend.app.db.database import normalize_database_url

    return normalize_database_url(config.get_main_option("sqlalchemy.url") or settings.database_url)


def _run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The application passes its own connection so migrations share its engine settings.
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = create_engine(_database_url())
    try:
        with engine.connect() as new_connection:
            _run(new_connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
