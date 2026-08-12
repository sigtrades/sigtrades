"""route rule is_active for per-pipeline pause

Revision ID: 008_route_rule_is_active
Revises: 007_membership_stripe_billing
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "008_route_rule_is_active"
down_revision = "007_membership_stripe_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_route_rules" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_route_rules")}
    if "is_active" not in cols:
        op.add_column(
            "user_route_rules",
            sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_route_rules" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_route_rules")}
    if "is_active" in cols:
        op.drop_column("user_route_rules", "is_active")
