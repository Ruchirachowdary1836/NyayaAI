"""Store API-computed dense embeddings in the database.

Revision ID: 0003_embedding_batches
Revises: 0002_platform_tables
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_embedding_batches"
down_revision = "0002_platform_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_batches",
        sa.Column("cache_key", sa.String(64), primary_key=True),
        sa.Column("batch_index", sa.Integer, primary_key=True),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("dimensions", sa.Integer, nullable=False),
        sa.Column("vectors", sa.LargeBinary, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("embedding_batches")
