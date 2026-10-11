"""SQLAlchemy Core table definitions.

The schema is created and evolved only through Alembic migrations in
``backend/app/db/migrations``; these definitions mirror the latest revision so
queries stay typed. Usernames remain the user primary key for compatibility with
databases created before migrations existed; foreign keys cascade on rename.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
    true,
)

metadata = MetaData()

users = Table(
    "users",
    metadata,
    Column("username", String(80), primary_key=True),
    Column("password_hash", LargeBinary, nullable=False),
    Column("password_salt", LargeBinary, nullable=False),
    Column("role", String(8), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("is_active", Boolean, nullable=False, server_default=true()),
    Column("last_login_at", DateTime(timezone=True)),
    # Access tokens issued before this instant are rejected (password change, deactivation).
    Column("tokens_valid_after", DateTime(timezone=True)),
    CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
)

feedback = Table(
    "feedback",
    metadata,
    Column("feedback_id", String(36), primary_key=True),
    Column("query", Text, nullable=False),
    Column("rating", String(4), nullable=False),
    Column("correctness", Integer),
    Column("comment", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("username", String(80)),
    CheckConstraint("rating IN ('up', 'down')", name="ck_feedback_rating"),
)

revoked_tokens = Table(
    "revoked_tokens",
    metadata,
    Column("jti", String(64), primary_key=True),
    Column("username", String(80), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Index("ix_revoked_tokens_expires_at", "expires_at"),
)

user_documents = Table(
    "user_documents",
    metadata,
    Column("document_id", String(36), primary_key=True),
    Column(
        "owner",
        String(80),
        ForeignKey("users.username", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("title", String(200), nullable=False),
    Column("filename", String(255), nullable=False),
    Column("content_type", String(100), nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("error", Text),
    Column("text", Text),
    Column("page_count", Integer),
    Column("char_count", Integer, nullable=False, server_default="0"),
    Column("content", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('processing', 'ready', 'failed')", name="ck_user_documents_status"),
    UniqueConstraint("owner", "sha256", name="uq_user_documents_owner_sha256"),
    Index("ix_user_documents_owner_created", "owner", "created_at"),
)

experiments = Table(
    "experiments",
    metadata,
    Column("experiment_id", String(36), primary_key=True),
    Column(
        "owner",
        String(80),
        ForeignKey("users.username", onupdate="CASCADE", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("name", String(120), nullable=False),
    Column("status", String(16), nullable=False),
    Column("config", JSON, nullable=False),
    Column("results", JSON, nullable=False),
    Column("summary", JSON, nullable=False),
    Column("duration_ms", Float, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("status IN ('completed', 'partial', 'failed')", name="ck_experiments_status"),
    Index("ix_experiments_owner_created", "owner", "created_at"),
)

usage_events = Table(
    "usage_events",
    metadata,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(80)),
    Column("event_type", String(24), nullable=False),
    Column("retriever", String(16)),
    Column("status", String(16), nullable=False),
    Column("result_count", Integer),
    Column("latency_ms", Float),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Index("ix_usage_events_created_at", "created_at"),
    Index("ix_usage_events_username", "username"),
)

# Dense vectors computed through an embeddings API, stored in batches so a long
# corpus build can resume after restarts and survive redeploys on ephemeral disks.
embedding_batches = Table(
    "embedding_batches",
    metadata,
    Column("cache_key", String(64), primary_key=True),
    Column("batch_index", Integer, primary_key=True),
    Column("row_count", Integer, nullable=False),
    Column("dimensions", Integer, nullable=False),
    Column("vectors", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
