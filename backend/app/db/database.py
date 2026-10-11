from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, delete, event, func, insert, select, text, update
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from backend.app.db.tables import (
    embedding_batches,
    experiments,
    feedback,
    metadata,
    revoked_tokens,
    usage_events,
    user_documents,
    users,
)

_MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

__all__ = [
    "Database",
    "DatabaseConfig",
    "DuplicateRecordError",
    "as_database",
    "isoformat",
    "metadata",
    "normalize_database_url",
    "utcnow",
]


class DuplicateRecordError(Exception):
    """Raised when a uniqueness constraint rejects an insert."""


def utcnow() -> datetime:
    return datetime.now(UTC)


def isoformat(value: datetime | None) -> str | None:
    """Render timestamps consistently; SQLite returns naive values that are stored as UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def normalize_database_url(url: str) -> str:
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.removeprefix("postgres://")
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.removeprefix("postgresql://")
    return url


# Retained for callers and tests that used the private name.
_normalize_database_url = normalize_database_url


def _enable_sqlite_foreign_keys(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    def __init__(self, url: str) -> None:
        url = normalize_database_url(url)
        self.is_sqlite = url.startswith("sqlite:")
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = create_engine_for(url)
        if self.is_sqlite:
            event.listen(self.engine, "connect", _enable_sqlite_foreign_keys)

    @classmethod
    def from_path(cls, path: Path) -> Database:
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(
            URL.create("sqlite", database=str(path.resolve())).render_as_string(hide_password=False)
        )

    # ------------------------------------------------------------------ lifecycle
    def initialize(self) -> None:
        """Apply all Alembic migrations up to the latest revision."""
        from alembic import command
        from alembic.config import Config

        config = Config()
        config.set_main_option("script_location", str(_MIGRATIONS_DIR))
        with self.engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")

    def schema_revision(self) -> str | None:
        with self.engine.connect() as connection:
            try:
                return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            except Exception:
                return None

    def ping(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    def close(self) -> None:
        self.engine.dispose()

    # ---------------------------------------------------------------------- users
    def create_user(
        self, username: str, password_hash: bytes, password_salt: bytes, role: str
    ) -> bool:
        try:
            with self.engine.begin() as connection:
                exists = connection.execute(
                    select(users.c.username).where(users.c.username == username)
                ).first()
                if exists:
                    return False
                connection.execute(
                    insert(users).values(
                        username=username,
                        password_hash=password_hash,
                        password_salt=password_salt,
                        role=role,
                        created_at=utcnow(),
                        is_active=True,
                    )
                )
        except IntegrityError:
            return False
        return True

    def get_user_credentials(self, username: str):
        with self.engine.connect() as connection:
            return connection.execute(
                select(
                    users.c.password_hash,
                    users.c.password_salt,
                    users.c.role,
                    users.c.is_active,
                ).where(users.c.username == username)
            ).first()

    def get_user_role(self, username: str) -> str | None:
        """Return the role of an active account, or ``None`` if it is missing or disabled."""
        with self.engine.connect() as connection:
            row = connection.execute(
                select(users.c.role, users.c.is_active).where(users.c.username == username)
            ).first()
        return str(row.role) if row and row.is_active else None

    def get_user_auth_state(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(users.c.role, users.c.is_active, users.c.tokens_valid_after).where(
                    users.c.username == username
                )
            ).first()
        if row is None:
            return None
        valid_after = row.tokens_valid_after
        if valid_after is not None and valid_after.tzinfo is None:
            valid_after = valid_after.replace(tzinfo=UTC)
        return {
            "role": str(row.role),
            "is_active": bool(row.is_active),
            "tokens_valid_after": valid_after,
        }

    def record_login(self, username: str) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                update(users).where(users.c.username == username).values(last_login_at=utcnow())
            )

    def update_user_credentials(
        self,
        current_username: str,
        new_username: str,
        password_hash: bytes | None = None,
        password_salt: bytes | None = None,
    ) -> bool:
        values: dict[str, object] = {"username": new_username}
        if password_hash is not None and password_salt is not None:
            values.update(
                password_hash=password_hash,
                password_salt=password_salt,
                tokens_valid_after=_token_cutoff(),
            )
        try:
            with self.engine.begin() as connection:
                result = connection.execute(
                    update(users).where(users.c.username == current_username).values(**values)
                )
        except IntegrityError:
            return False
        return result.rowcount == 1

    def get_user_profile(self, username: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(
                    users.c.username,
                    users.c.role,
                    users.c.is_active,
                    users.c.created_at,
                    users.c.last_login_at,
                ).where(users.c.username == username)
            ).first()
        return _user_dict(row) if row else None

    def list_users(
        self, limit: int = 50, offset: int = 0, query: str | None = None
    ) -> tuple[list[dict[str, Any]], int]:
        condition = users.c.username.contains(query, autoescape=True) if query else None
        statement = select(
            users.c.username,
            users.c.role,
            users.c.is_active,
            users.c.created_at,
            users.c.last_login_at,
        ).order_by(users.c.created_at.desc(), users.c.username)
        count = select(func.count()).select_from(users)
        if condition is not None:
            statement = statement.where(condition)
            count = count.where(condition)
        with self.engine.connect() as connection:
            rows = connection.execute(statement.limit(limit).offset(offset)).all()
            total = int(connection.execute(count).scalar_one())
        return [_user_dict(row) for row in rows], total

    def count_users(self, active_only: bool = False) -> int:
        statement = select(func.count()).select_from(users)
        if active_only:
            statement = statement.where(users.c.is_active.is_(True))
        with self.engine.connect() as connection:
            return int(connection.execute(statement).scalar_one())

    def count_active_admins(self) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.execute(
                    select(func.count())
                    .select_from(users)
                    .where(users.c.role == "admin", users.c.is_active.is_(True))
                ).scalar_one()
            )

    def update_user_access(
        self, username: str, role: str | None = None, is_active: bool | None = None
    ) -> bool:
        values: dict[str, object] = {}
        if role is not None:
            values["role"] = role
        if is_active is not None:
            values["is_active"] = is_active
        if values:
            # Role changes and deactivation invalidate every session issued before now.
            values["tokens_valid_after"] = _token_cutoff()
        if not values:
            return self.get_user_profile(username) is not None
        with self.engine.begin() as connection:
            result = connection.execute(
                update(users).where(users.c.username == username).values(**values)
            )
        return result.rowcount == 1

    # --------------------------------------------------------------------- tokens
    def revoke_token(self, jti: str, username: str, expires_at: datetime) -> None:
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(revoked_tokens).values(jti=jti, username=username, expires_at=expires_at)
                )
        except IntegrityError:
            return  # Already revoked.

    def is_token_revoked(self, jti: str) -> bool:
        with self.engine.connect() as connection:
            return (
                connection.execute(
                    select(revoked_tokens.c.jti).where(revoked_tokens.c.jti == jti)
                ).first()
                is not None
            )

    def purge_expired_tokens(self) -> int:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(revoked_tokens).where(revoked_tokens.c.expires_at < utcnow())
            )
        return int(result.rowcount or 0)

    # ------------------------------------------------------------------- feedback
    def insert_feedback(
        self,
        feedback_id: str,
        query: str,
        rating: str,
        correctness: int | None,
        comment: str | None,
        username: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(feedback).values(
                    feedback_id=feedback_id,
                    query=query,
                    rating=rating,
                    correctness=correctness,
                    comment=comment,
                    username=username,
                    created_at=utcnow(),
                )
            )

    def count_feedback(self) -> dict[str, int]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(feedback.c.rating, func.count()).group_by(feedback.c.rating)
            ).all()
        return {str(rating): int(count) for rating, count in rows}

    # ------------------------------------------------------------- user documents
    _DOCUMENT_SUMMARY = (
        user_documents.c.document_id,
        user_documents.c.owner,
        user_documents.c.title,
        user_documents.c.filename,
        user_documents.c.content_type,
        user_documents.c.size_bytes,
        user_documents.c.sha256,
        user_documents.c.status,
        user_documents.c.error,
        user_documents.c.page_count,
        user_documents.c.char_count,
        user_documents.c.created_at,
        user_documents.c.updated_at,
    )

    def insert_user_document(self, record: Mapping[str, Any]) -> None:
        now = utcnow()
        try:
            with self.engine.begin() as connection:
                connection.execute(
                    insert(user_documents).values(**record, created_at=now, updated_at=now)
                )
        except IntegrityError as error:
            raise DuplicateRecordError("This file is already in your library") from error

    def find_user_document_by_hash(self, owner: str, sha256: str) -> str | None:
        with self.engine.connect() as connection:
            return connection.execute(
                select(user_documents.c.document_id).where(
                    user_documents.c.owner == owner, user_documents.c.sha256 == sha256
                )
            ).scalar_one_or_none()

    def list_user_documents(
        self,
        owner: str,
        limit: int = 20,
        offset: int = 0,
        query: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        conditions = [user_documents.c.owner == owner]
        if query:
            conditions.append(
                func.lower(user_documents.c.title).contains(query.casefold(), autoescape=True)
                | func.lower(user_documents.c.filename).contains(query.casefold(), autoescape=True)
            )
        if status:
            conditions.append(user_documents.c.status == status)
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(*self._DOCUMENT_SUMMARY)
                .where(*conditions)
                .order_by(user_documents.c.created_at.desc(), user_documents.c.document_id)
                .limit(limit)
                .offset(offset)
            ).all()
            total = int(
                connection.execute(
                    select(func.count()).select_from(user_documents).where(*conditions)
                ).scalar_one()
            )
        return [_document_dict(row) for row in rows], total

    def get_user_document(
        self, owner: str, document_id: str, include_content: bool = False
    ) -> dict[str, Any] | None:
        columns = [*self._DOCUMENT_SUMMARY, user_documents.c.text]
        if include_content:
            columns.append(user_documents.c.content)
        with self.engine.connect() as connection:
            row = connection.execute(
                select(*columns).where(
                    user_documents.c.owner == owner, user_documents.c.document_id == document_id
                )
            ).first()
        if row is None:
            return None
        result = _document_dict(row)
        result["text"] = row.text
        if include_content:
            result["content"] = bytes(row.content)
        return result

    def list_ready_document_texts(self, owner: str) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    user_documents.c.document_id,
                    user_documents.c.title,
                    user_documents.c.filename,
                    user_documents.c.text,
                ).where(user_documents.c.owner == owner, user_documents.c.status == "ready")
            ).all()
        return [dict(row._mapping) for row in rows]

    def delete_user_document(self, owner: str, document_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(user_documents).where(
                    user_documents.c.owner == owner, user_documents.c.document_id == document_id
                )
            )
        return result.rowcount == 1

    def count_user_documents(self, owner: str | None = None) -> dict[str, int]:
        statement = select(user_documents.c.status, func.count()).group_by(user_documents.c.status)
        if owner is not None:
            statement = statement.where(user_documents.c.owner == owner)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).all()
        return {str(status): int(count) for status, count in rows}

    def total_user_document_bytes(self) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.execute(
                    select(func.coalesce(func.sum(user_documents.c.size_bytes), 0))
                ).scalar_one()
            )

    # ---------------------------------------------------------------- experiments
    def insert_experiment(self, record: Mapping[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(insert(experiments).values(**record, created_at=utcnow()))

    def list_experiments(
        self, owner: str, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    experiments.c.experiment_id,
                    experiments.c.name,
                    experiments.c.status,
                    experiments.c.config,
                    experiments.c.summary,
                    experiments.c.duration_ms,
                    experiments.c.created_at,
                )
                .where(experiments.c.owner == owner)
                .order_by(experiments.c.created_at.desc(), experiments.c.experiment_id)
                .limit(limit)
                .offset(offset)
            ).all()
            total = int(
                connection.execute(
                    select(func.count())
                    .select_from(experiments)
                    .where(experiments.c.owner == owner)
                ).scalar_one()
            )
        return [_experiment_dict(row) for row in rows], total

    def get_experiment(self, owner: str, experiment_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                select(experiments).where(
                    experiments.c.owner == owner, experiments.c.experiment_id == experiment_id
                )
            ).first()
        if row is None:
            return None
        result = _experiment_dict(row)
        result["results"] = row.results
        return result

    def delete_experiment(self, owner: str, experiment_id: str) -> bool:
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(experiments).where(
                    experiments.c.owner == owner, experiments.c.experiment_id == experiment_id
                )
            )
        return result.rowcount == 1

    def count_experiments(self, owner: str | None = None) -> int:
        statement = select(func.count()).select_from(experiments)
        if owner is not None:
            statement = statement.where(experiments.c.owner == owner)
        with self.engine.connect() as connection:
            return int(connection.execute(statement).scalar_one())

    # ----------------------------------------------------------------- embeddings
    def save_embedding_batch(
        self, cache_key: str, batch_index: int, row_count: int, dimensions: int, vectors: bytes
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                delete(embedding_batches).where(
                    embedding_batches.c.cache_key == cache_key,
                    embedding_batches.c.batch_index == batch_index,
                )
            )
            connection.execute(
                insert(embedding_batches).values(
                    cache_key=cache_key,
                    batch_index=batch_index,
                    row_count=row_count,
                    dimensions=dimensions,
                    vectors=vectors,
                    created_at=utcnow(),
                )
            )

    def load_embedding_batches(self, cache_key: str) -> dict[int, tuple[int, int, bytes]]:
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    embedding_batches.c.batch_index,
                    embedding_batches.c.row_count,
                    embedding_batches.c.dimensions,
                    embedding_batches.c.vectors,
                ).where(embedding_batches.c.cache_key == cache_key)
            ).all()
        return {
            int(row.batch_index): (int(row.row_count), int(row.dimensions), bytes(row.vectors))
            for row in rows
        }

    def delete_stale_embeddings(self, keep_cache_key: str) -> int:
        """Remove vectors for corpora or models that are no longer in use."""
        with self.engine.begin() as connection:
            result = connection.execute(
                delete(embedding_batches).where(embedding_batches.c.cache_key != keep_cache_key)
            )
        return int(result.rowcount or 0)

    # ---------------------------------------------------------------------- usage
    def record_usage(
        self,
        username: str | None,
        event_type: str,
        status: str,
        retriever: str | None = None,
        result_count: int | None = None,
        latency_ms: float | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                insert(usage_events).values(
                    username=username,
                    event_type=event_type,
                    retriever=retriever,
                    status=status,
                    result_count=result_count,
                    latency_ms=latency_ms,
                    created_at=utcnow(),
                )
            )

    def usage_summary(self, since: datetime, username: str | None = None) -> list[dict[str, Any]]:
        conditions = [usage_events.c.created_at >= since]
        if username is not None:
            conditions.append(usage_events.c.username == username)
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    usage_events.c.event_type,
                    usage_events.c.retriever,
                    usage_events.c.status,
                    func.count().label("count"),
                    func.avg(usage_events.c.latency_ms).label("avg_latency_ms"),
                )
                .where(*conditions)
                .group_by(
                    usage_events.c.event_type, usage_events.c.retriever, usage_events.c.status
                )
                .order_by(usage_events.c.event_type, usage_events.c.retriever)
            ).all()
        return [
            {
                "event_type": row.event_type,
                "retriever": row.retriever,
                "status": row.status,
                "count": int(row.count),
                "avg_latency_ms": (
                    round(float(row.avg_latency_ms), 2) if row.avg_latency_ms is not None else None
                ),
            }
            for row in rows
        ]

    def active_user_count(self, since: datetime) -> int:
        with self.engine.connect() as connection:
            return int(
                connection.execute(
                    select(func.count(func.distinct(usage_events.c.username))).where(
                        usage_events.c.created_at >= since, usage_events.c.username.is_not(None)
                    )
                ).scalar_one()
            )


def _token_cutoff() -> datetime:
    # JWT ``iat`` claims have whole-second precision, so the cutoff is truncated to match.
    return utcnow().replace(microsecond=0)


def create_engine_for(url: str) -> Engine:
    from sqlalchemy import create_engine

    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if url.startswith("sqlite:") else {},
    )


def _user_dict(row) -> dict[str, Any]:
    return {
        "username": str(row.username),
        "role": str(row.role),
        "is_active": bool(row.is_active),
        "created_at": isoformat(row.created_at),
        "last_login_at": isoformat(row.last_login_at),
    }


def _document_dict(row) -> dict[str, Any]:
    return {
        "document_id": row.document_id,
        "owner": row.owner,
        "title": row.title,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": int(row.size_bytes),
        "sha256": row.sha256,
        "status": row.status,
        "error": row.error,
        "page_count": row.page_count,
        "char_count": int(row.char_count or 0),
        "created_at": isoformat(row.created_at),
        "updated_at": isoformat(row.updated_at),
    }


def _experiment_dict(row) -> dict[str, Any]:
    return {
        "experiment_id": row.experiment_id,
        "name": row.name,
        "status": row.status,
        "config": row.config,
        "summary": row.summary,
        "duration_ms": float(row.duration_ms),
        "created_at": isoformat(row.created_at),
    }


DatabaseConfig = str | Path | Database


def as_database(value: DatabaseConfig) -> Database:
    if isinstance(value, Database):
        return value
    return Database.from_path(value) if isinstance(value, Path) else Database(value)
