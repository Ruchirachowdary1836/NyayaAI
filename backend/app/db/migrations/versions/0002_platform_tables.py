"""Account status, token revocation, user documents, experiments, and usage events.

Revision ID: 0002_platform_tables
Revises: 0001_baseline
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_platform_tables"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("tokens_valid_after", sa.DateTime(timezone=True)))
    op.add_column("feedback", sa.Column("username", sa.String(80)))

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(64), primary_key=True),
        sa.Column("username", sa.String(80), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    op.create_table(
        "user_documents",
        sa.Column("document_id", sa.String(36), primary_key=True),
        sa.Column(
            "owner",
            sa.String(80),
            sa.ForeignKey("users.username", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text),
        sa.Column("text", sa.Text),
        sa.Column("page_count", sa.Integer),
        sa.Column("char_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.LargeBinary, nullable=False),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        sa.CheckConstraint(
            "status IN ('processing', 'ready', 'failed')", name="ck_user_documents_status"
        ),
        sa.UniqueConstraint("owner", "sha256", name="uq_user_documents_owner_sha256"),
    )
    op.create_index("ix_user_documents_owner_created", "user_documents", ["owner", "created_at"])

    op.create_table(
        "experiments",
        sa.Column("experiment_id", sa.String(36), primary_key=True),
        sa.Column(
            "owner",
            sa.String(80),
            sa.ForeignKey("users.username", onupdate="CASCADE", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("results", sa.JSON, nullable=False),
        sa.Column("summary", sa.JSON, nullable=False),
        sa.Column("duration_ms", sa.Float, nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'failed')", name="ck_experiments_status"
        ),
    )
    op.create_index("ix_experiments_owner_created", "experiments", ["owner", "created_at"])

    op.create_table(
        "usage_events",
        sa.Column("event_id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(80)),
        sa.Column("event_type", sa.String(24), nullable=False),
        sa.Column("retriever", sa.String(16)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result_count", sa.Integer),
        sa.Column("latency_ms", sa.Float),
        _timestamp("created_at"),
    )
    op.create_index("ix_usage_events_created_at", "usage_events", ["created_at"])
    op.create_index("ix_usage_events_username", "usage_events", ["username"])


def downgrade() -> None:
    op.drop_table("usage_events")
    op.drop_table("experiments")
    op.drop_table("user_documents")
    op.drop_table("revoked_tokens")
    with op.batch_alter_table("feedback") as batch:
        batch.drop_column("username")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("tokens_valid_after")
        batch.drop_column("last_login_at")
        batch.drop_column("is_active")
