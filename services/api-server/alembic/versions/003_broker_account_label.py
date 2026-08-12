"""broker account label: unique identifier per user

Revision ID: 003_broker_account_label
Revises: 002_route_default_quantity
Create Date: 2026-06-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect, text

revision = "003_broker_account_label"
down_revision = "002_route_default_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "broker_credentials" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("broker_credentials")}
        if "label" not in cols:
            op.add_column("broker_credentials", sa.Column("label", sa.String(64), nullable=True))
        bind.execute(text(
            "UPDATE broker_credentials SET label = COALESCE(NULLIF(config->>'label', ''), NULLIF(account_id, ''), broker) "
            "WHERE label IS NULL OR label = ''"
        ))
        bind.execute(text("UPDATE broker_credentials SET label = broker || '-' || id::text WHERE label IS NULL OR label = ''"))
        op.alter_column("broker_credentials", "label", nullable=False, server_default="")
        constraints = {c["name"] for c in inspector.get_unique_constraints("broker_credentials")}
        if "uq_broker_cred" in constraints:
            op.drop_constraint("uq_broker_cred", "broker_credentials", type_="unique")
        constraints = {c["name"] for c in inspect(bind).get_unique_constraints("broker_credentials")}
        if "uq_broker_cred_label" not in constraints:
            op.create_unique_constraint("uq_broker_cred_label", "broker_credentials", ["user_id", "label"])

    if "user_broker_bindings" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("user_broker_bindings")}
        if "label" not in cols:
            op.add_column("user_broker_bindings", sa.Column("label", sa.String(64), nullable=True))
        bind.execute(text(
            "UPDATE user_broker_bindings SET label = NULLIF(account_id, '') WHERE label IS NULL OR label = ''"
        ))
        bind.execute(text(
            "UPDATE user_broker_bindings SET label = broker || '-' || id::text WHERE label IS NULL OR label = ''"
        ))
        op.alter_column("user_broker_bindings", "label", nullable=False, server_default="")
        constraints = {c["name"] for c in inspect(bind).get_unique_constraints("user_broker_bindings")}
        if "uq_broker_binding_label" not in constraints:
            op.create_unique_constraint("uq_broker_binding_label", "user_broker_bindings", ["user_id", "label"])

    if "user_route_rules" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("user_route_rules")}
        if "account_label" not in cols:
            op.add_column("user_route_rules", sa.Column("account_label", sa.String(64), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "user_route_rules" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("user_route_rules")}
        if "account_label" in cols:
            op.drop_column("user_route_rules", "account_label")

    if "user_broker_bindings" in inspector.get_table_names():
        constraints = {c["name"] for c in inspector.get_unique_constraints("user_broker_bindings")}
        if "uq_broker_binding_label" in constraints:
            op.drop_constraint("uq_broker_binding_label", "user_broker_bindings", type_="unique")
        cols = {c["name"] for c in inspector.get_columns("user_broker_bindings")}
        if "label" in cols:
            op.drop_column("user_broker_bindings", "label")

    if "broker_credentials" in inspector.get_table_names():
        constraints = {c["name"] for c in inspector.get_unique_constraints("broker_credentials")}
        if "uq_broker_cred_label" in constraints:
            op.drop_constraint("uq_broker_cred_label", "broker_credentials", type_="unique")
        cols = {c["name"] for c in inspector.get_columns("broker_credentials")}
        if "label" in cols:
            op.drop_column("broker_credentials", "label")
        constraints = {c["name"] for c in inspect(bind).get_unique_constraints("broker_credentials")}
        if "uq_broker_cred" not in constraints:
            op.create_unique_constraint("uq_broker_cred", "broker_credentials", ["user_id", "broker", "account_id"])
