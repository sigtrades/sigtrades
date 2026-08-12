"""execution record account_label

Revision ID: 004_execution_account_label
Revises: 003_broker_account_label
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "004_execution_account_label"
down_revision = "003_broker_account_label"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("execution_records")}
    if "account_label" not in cols:
        op.add_column("execution_records", sa.Column("account_label", sa.String(64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("execution_records")}
    if "account_label" in cols:
        op.drop_column("execution_records", "account_label")
