"""baseline: 全量 schema（与 app.models 一致）

Revision ID: 001_baseline
Revises:
Create Date: 2026-06-06
"""

from __future__ import annotations

from alembic import op
from sqlalchemy import inspect

from app.database import Base
import app.models  # noqa: F401

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            table.create(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(Base.metadata.sorted_tables):
        table.drop(bind, checkfirst=True)
