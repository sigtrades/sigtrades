"""user display_name

Revision ID: 005_user_display_name
Revises: 004_execution_account_label
Create Date: 2026-06-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "005_user_display_name"
down_revision = "004_execution_account_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "display_name" not in cols:
        op.add_column("users", sa.Column("display_name", sa.String(64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "users" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("users")}
    if "display_name" in cols:
        op.drop_column("users", "display_name")
