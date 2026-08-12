"""user_broker_bindings.config for last_probe persistence

Revision ID: 011_binding_config
Revises: 010_agent_connect_sessions
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "011_binding_config"
down_revision = "010_agent_connect_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_broker_bindings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_broker_bindings")}
    if "config" not in cols:
        op.add_column(
            "user_broker_bindings",
            sa.Column("config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "user_broker_bindings" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("user_broker_bindings")}
    if "config" in cols:
        op.drop_column("user_broker_bindings", "config")
