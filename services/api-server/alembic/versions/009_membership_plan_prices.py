"""membership plan display prices

Revision ID: 009_membership_plan_prices
Revises: 008_route_rule_is_active
Create Date: 2026-07-02
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "009_membership_plan_prices"
down_revision = "008_route_rule_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "price_monthly" not in cols:
        op.add_column(
            "membership_plans",
            sa.Column("price_monthly", sa.Numeric(10, 2), nullable=True),
        )
    if "price_yearly" not in cols:
        op.add_column(
            "membership_plans",
            sa.Column("price_yearly", sa.Numeric(10, 2), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE membership_plans SET price_monthly = 9.00, price_yearly = 90.00
            WHERE code = 'starter' AND price_monthly IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE membership_plans SET price_monthly = 19.00, price_yearly = 190.00
            WHERE code = 'pro' AND price_monthly IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "price_yearly" in cols:
        op.drop_column("membership_plans", "price_yearly")
    if "price_monthly" in cols:
        op.drop_column("membership_plans", "price_monthly")
