"""admin ops tables + user/agent columns

Revision ID: 006_admin_ops_tables
Revises: 005_user_display_name
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "006_admin_ops_tables"
down_revision = "005_user_display_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "users" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "is_banned" not in cols:
            op.add_column("users", sa.Column("is_banned", sa.Boolean(), server_default="false", nullable=False))
        if "admin_note" not in cols:
            op.add_column("users", sa.Column("admin_note", sa.Text(), nullable=True))

    if "agent_tokens" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("agent_tokens")}
        if "revoked_at" not in cols:
            op.add_column("agent_tokens", sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        if "last_seen_at" not in cols:
            op.add_column("agent_tokens", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))

    tables = set(inspector.get_table_names())

    if "promotions" not in tables:
        op.create_table(
            "promotions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("kind", sa.String(30), nullable=False, index=True),
            sa.Column("code", sa.String(50), nullable=True, unique=True, index=True),
            sa.Column("reward_kind", sa.String(20), nullable=False, server_default="membership_days"),
            sa.Column("amount_usd", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("referrer_amount_usd", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("membership_days", sa.Integer(), server_default="0", nullable=False),
            sa.Column("membership_plan_code", sa.String(20), nullable=True),
            sa.Column("referrer_membership_days", sa.Integer(), server_default="0", nullable=False),
            sa.Column("referrer_membership_plan_code", sa.String(20), nullable=True),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("current_uses", sa.Integer(), server_default="0", nullable=False),
            sa.Column("max_uses_per_user", sa.Integer(), server_default="1", nullable=False),
            sa.Column("require_email_verified", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("require_referrer", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
            sa.Column("created_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "promotion_redemptions" not in tables:
        op.create_table(
            "promotion_redemptions",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("promotion_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("promotions.id", ondelete="RESTRICT"), nullable=False, index=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("amount_usd", sa.Numeric(12, 2), server_default="0", nullable=False),
            sa.Column("fee_record_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("role", sa.String(20), server_default="receiver", nullable=False),
            sa.Column("meta", postgresql.JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )
        op.create_index("ix_promotion_redemptions_pu", "promotion_redemptions", ["promotion_id", "user_id"])

    if "in_app_broadcasts" not in tables:
        op.create_table(
            "in_app_broadcasts",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("title_zh", sa.String(200), server_default="", nullable=False),
            sa.Column("title_en", sa.String(200), server_default="", nullable=False),
            sa.Column("body_md_zh", sa.Text(), server_default="", nullable=False),
            sa.Column("body_md_en", sa.Text(), server_default="", nullable=False),
            sa.Column("send_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("first_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("email_audience", sa.String(20), server_default="none", nullable=False),
            sa.Column("email_sent_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("email_send_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("email_recipients", sa.Integer(), server_default="0", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "user_notifications" not in tables:
        op.create_table(
            "user_notifications",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("type", sa.String(50), nullable=False, index=True),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("message_format", sa.String(20), server_default="plain", nullable=False),
            sa.Column("ref_id", sa.String(100), nullable=True),
            sa.Column("is_read", sa.Boolean(), server_default="false", nullable=False, index=True),
            sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        )

    if "admin_settings" not in tables:
        op.create_table(
            "admin_settings",
            sa.Column("key", sa.String(128), primary_key=True),
            sa.Column("value", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )

    if "admin_audit_logs" not in tables:
        op.create_table(
            "admin_audit_logs",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("admin_username", sa.String(100), nullable=False, index=True),
            sa.Column("admin_role", sa.String(32), server_default="admin", nullable=False),
            sa.Column("action", sa.String(64), nullable=False, index=True),
            sa.Column("target_type", sa.String(64), nullable=True),
            sa.Column("target_id", sa.String(128), nullable=True),
            sa.Column("meta", postgresql.JSONB(), server_default="{}", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False, index=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    for table in (
        "admin_audit_logs",
        "admin_settings",
        "user_notifications",
        "in_app_broadcasts",
        "promotion_redemptions",
        "promotions",
    ):
        if table in tables:
            op.drop_table(table)

    if "agent_tokens" in tables:
        cols = {c["name"] for c in inspector.get_columns("agent_tokens")}
        if "last_seen_at" in cols:
            op.drop_column("agent_tokens", "last_seen_at")
        if "revoked_at" in cols:
            op.drop_column("agent_tokens", "revoked_at")

    if "users" in tables:
        cols = {c["name"] for c in inspector.get_columns("users")}
        if "admin_note" in cols:
            op.drop_column("users", "admin_note")
        if "is_banned" in cols:
            op.drop_column("users", "is_banned")
