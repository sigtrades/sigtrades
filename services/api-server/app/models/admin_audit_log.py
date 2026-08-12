"""后台操作审计日志。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    admin_username: Mapped[str] = mapped_column(String(100), index=True)
    admin_role: Mapped[str] = mapped_column(String(32), default="admin")
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "admin_username": self.admin_username,
            "admin_role": self.admin_role,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "meta": self.meta or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
