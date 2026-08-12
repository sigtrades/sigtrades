"""全站/产品公告广播。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class InAppBroadcast(Base):
    __tablename__ = "in_app_broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    title_zh: Mapped[str] = mapped_column(String(200), default="")
    title_en: Mapped[str] = mapped_column(String(200), default="")
    body_md_zh: Mapped[str] = mapped_column(Text, default="")
    body_md_en: Mapped[str] = mapped_column(Text, default="")
    send_count: Mapped[int] = mapped_column(Integer, default=0)
    first_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_audience: Mapped[str] = mapped_column(String(20), default="none")
    email_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    email_send_count: Mapped[int] = mapped_column(Integer, default=0)
    email_recipients: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "title_zh": self.title_zh or "",
            "title_en": self.title_en or "",
            "body_md_zh": self.body_md_zh or "",
            "body_md_en": self.body_md_en or "",
            "send_count": int(self.send_count or 0),
            "first_sent_at": self.first_sent_at.isoformat() if self.first_sent_at else None,
            "last_sent_at": self.last_sent_at.isoformat() if self.last_sent_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "email_audience": self.email_audience or "none",
            "email_sent_at": self.email_sent_at.isoformat() if self.email_sent_at else None,
            "email_send_count": int(self.email_send_count or 0),
            "email_recipients": int(self.email_recipients or 0),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
