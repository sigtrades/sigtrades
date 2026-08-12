"""membership plan is_active for public visibility

Revision ID: 012_membership_plan_is_active
Revises: 011_binding_config
Create Date: 2026-07-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "012_membership_plan_is_active"
down_revision = "011_binding_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "is_active" not in cols:
        op.add_column(
            "membership_plans",
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "is_active" in cols:
        op.drop_column("membership_plans", "is_active")
