"""server-side Relay Agent browser login sessions

Revision ID: 010_agent_connect_sessions
Revises: 009_membership_plan_prices
Create Date: 2026-07-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "010_agent_connect_sessions"
down_revision = "009_membership_plan_prices"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "agent_connect_sessions" in inspector.get_table_names():
        return

    op.create_table(
        "agent_connect_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("device_id", sa.String(64), nullable=False),
        sa.Column("poll_secret_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("pending_token_encrypted", sa.Text(), nullable=True),
        sa.Column("legacy_callback_port", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("authorized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_agent_connect_sessions_device_id", "agent_connect_sessions", ["device_id"])
    op.create_index(
        "ix_agent_connect_sessions_poll_secret_hash",
        "agent_connect_sessions",
        ["poll_secret_hash"],
        unique=True,
    )
    op.create_index("ix_agent_connect_sessions_status", "agent_connect_sessions", ["status"])
    op.create_index("ix_agent_connect_sessions_expires_at", "agent_connect_sessions", ["expires_at"])


def downgrade() -> None:
    bind = op.get_bind()
    if "agent_connect_sessions" in inspect(bind).get_table_names():
        op.drop_table("agent_connect_sessions")
