"""membership plan monthly/yearly stripe price ids

Revision ID: 007_membership_stripe_billing
Revises: 006_admin_ops_tables
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "007_membership_stripe_billing"
down_revision = "006_admin_ops_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "stripe_price_id_monthly" not in cols:
        op.add_column(
            "membership_plans",
            sa.Column("stripe_price_id_monthly", sa.String(length=128), nullable=True),
        )
    if "stripe_price_id_yearly" not in cols:
        op.add_column(
            "membership_plans",
            sa.Column("stripe_price_id_yearly", sa.String(length=128), nullable=True),
        )

    op.execute(
        sa.text(
            """
            UPDATE membership_plans
            SET stripe_price_id_monthly = stripe_price_id
            WHERE stripe_price_id IS NOT NULL
              AND stripe_price_id_monthly IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "membership_plans" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("membership_plans")}
    if "stripe_price_id_yearly" in cols:
        op.drop_column("membership_plans", "stripe_price_id_yearly")
    if "stripe_price_id_monthly" in cols:
        op.drop_column("membership_plans", "stripe_price_id_monthly")
