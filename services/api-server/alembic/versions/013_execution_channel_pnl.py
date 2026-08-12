"""execution_records channel_id / signal_subtype / realized_pnl

Revision ID: 013_execution_channel_pnl
Revises: 012_membership_plan_is_active
Create Date: 2026-08-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "013_execution_channel_pnl"
down_revision = "012_membership_plan_is_active"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("execution_records")}
    if "channel_id" not in cols:
        op.add_column("execution_records", sa.Column("channel_id", sa.String(64), nullable=True))
        op.create_index("ix_execution_records_channel_id", "execution_records", ["channel_id"])
    if "signal_subtype" not in cols:
        op.add_column("execution_records", sa.Column("signal_subtype", sa.String(32), nullable=True))
    if "realized_pnl" not in cols:
        op.add_column("execution_records", sa.Column("realized_pnl", sa.Numeric(18, 6), nullable=True))

    # 历史回填：频道 / 子类型来自 signal JSON；盈亏取同 signal 最新有 pnl 的 report
    bind.execute(
        text(
            """
            UPDATE execution_records er
            SET
              channel_id = COALESCE(
                NULLIF(TRIM(er.signal->'metadata'->>'channel_id'), ''),
                NULLIF(TRIM(er.signal->'metadata'->>'chat_id'), '')
              ),
              signal_subtype = CASE
                WHEN UPPER(COALESCE(er.signal->>'signal_subtype', '')) IN ('ENTRY', 'OPEN') THEN 'OPEN'
                WHEN UPPER(COALESCE(er.signal->>'signal_subtype', '')) IN ('EXIT', 'CLOSE', 'STOP', 'INVALIDATION')
                  OR UPPER(COALESCE(er.signal->>'signal_subtype', '')) LIKE 'STOP_LOSS%' THEN 'CLOSE'
                WHEN NULLIF(TRIM(er.signal->>'signal_subtype'), '') IS NOT NULL
                  THEN LEFT(UPPER(TRIM(er.signal->>'signal_subtype')), 32)
                ELSE er.signal_subtype
              END
            WHERE er.signal IS NOT NULL
            """
        )
    )
    bind.execute(
        text(
            """
            UPDATE execution_records er
            SET realized_pnl = src.pnl
            FROM (
              SELECT DISTINCT ON (r.user_id, r.source_id, r.signal_id, COALESCE(r.account_id, ''))
                r.user_id,
                r.source_id,
                r.signal_id,
                r.account_id,
                (r.payload->>'realized_pnl')::double precision AS pnl
              FROM execution_reports r
              WHERE r.payload ? 'realized_pnl'
                AND NULLIF(TRIM(r.payload->>'realized_pnl'), '') IS NOT NULL
              ORDER BY r.user_id, r.source_id, r.signal_id, COALESCE(r.account_id, ''), r.created_at DESC
            ) src
            WHERE er.user_id = src.user_id
              AND er.source_id = src.source_id
              AND er.signal_id = src.signal_id
              AND COALESCE(er.account_id, '') = COALESCE(src.account_id, '')
              AND er.realized_pnl IS NULL
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "execution_records" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("execution_records")}
    if "realized_pnl" in cols:
        op.drop_column("execution_records", "realized_pnl")
    if "signal_subtype" in cols:
        op.drop_column("execution_records", "signal_subtype")
    if "channel_id" in cols:
        op.drop_index("ix_execution_records_channel_id", table_name="execution_records")
        op.drop_column("execution_records", "channel_id")
