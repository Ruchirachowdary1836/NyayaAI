"""Baseline users and feedback tables.

Databases created before migrations existed already contain these tables, so
this revision only creates what is missing and never alters existing data.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "users" not in existing:
        op.create_table(
            "users",
            sa.Column("username", sa.String(80), primary_key=True),
            sa.Column("password_hash", sa.LargeBinary, nullable=False),
            sa.Column("password_salt", sa.LargeBinary, nullable=False),
            sa.Column("role", sa.String(8), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint("role IN ('user', 'admin')", name="ck_users_role"),
        )
    if "feedback" not in existing:
        op.create_table(
            "feedback",
            sa.Column("feedback_id", sa.String(36), primary_key=True),
            sa.Column("query", sa.Text, nullable=False),
            sa.Column("rating", sa.String(4), nullable=False),
            sa.Column("correctness", sa.Integer),
            sa.Column("comment", sa.Text),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint("rating IN ('up', 'down')", name="ck_feedback_rating"),
        )


def downgrade() -> None:
    # Dropping user accounts is destructive, so the baseline is never downgraded automatically.
    raise RuntimeError("Downgrading the baseline revision would delete user data.")
