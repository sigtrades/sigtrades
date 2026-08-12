"""add default_quantity to user_route_rules

Revision ID: 002_route_default_quantity
Revises: 001_baseline
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "002_route_default_quantity"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_route_rules" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("user_route_rules")}
    if "default_quantity" not in columns:
        op.add_column("user_route_rules", sa.Column("default_quantity", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_route_rules" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("user_route_rules")}
    if "default_quantity" in columns:
        op.drop_column("user_route_rules", "default_quantity")
