"""活动/兑换码（促销）模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

PROMO_KIND_SIGNUP_BONUS = "signup_bonus"
PROMO_KIND_REFERRAL = "referral"
PROMO_KIND_CODE_PUBLIC = "code_public"
PROMO_KIND_CODE_PRIVATE = "code_private"
PROMO_KIND_CODE_ONEOFF = "code_oneoff"
# 合作方活动模板：code 字段存 campaign_key（如 sunnyquant_pro_gift），不可直接兑换
PROMO_KIND_PARTNER_CAMPAIGN = "partner_campaign"

ALL_PROMO_KINDS = {
    PROMO_KIND_SIGNUP_BONUS,
    PROMO_KIND_REFERRAL,
    PROMO_KIND_CODE_PUBLIC,
    PROMO_KIND_CODE_PRIVATE,
    PROMO_KIND_CODE_ONEOFF,
    PROMO_KIND_PARTNER_CAMPAIGN,
}
CODE_KINDS = {PROMO_KIND_CODE_PUBLIC, PROMO_KIND_CODE_PRIVATE, PROMO_KIND_CODE_ONEOFF}
# partner_campaign 的 code = campaign_key，需规范化但不进可兑换 CODE_KINDS
CAMPAIGN_KEY_KINDS = {PROMO_KIND_PARTNER_CAMPAIGN}


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Promotion(Base):
    __tablename__ = "promotions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(30), index=True)
    code: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    reward_kind: Mapped[str] = mapped_column(String(20), default="membership_days")
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    referrer_amount_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    membership_days: Mapped[int] = mapped_column(Integer, default=0)
    # 合作发码：绝对到期日（与 SQ 会员到期严格对齐）；优先于 membership_days
    membership_period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    membership_plan_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    referrer_membership_days: Mapped[int] = mapped_column(Integer, default=0)
    referrer_membership_plan_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    max_uses: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_uses: Mapped[int] = mapped_column(Integer, default=0)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1)
    require_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    require_referrer: Mapped[bool] = mapped_column(Boolean, default=False)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # 一次性合作码幂等键（如 sq_membership:<id>:<period_end>）
    partner_external_ref: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True, index=True)
    # 指向 partner_campaign 模板
    parent_promotion_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promotions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "code": self.code,
            "reward_kind": self.reward_kind or "membership_days",
            "amount_usd": float(self.amount_usd or 0),
            "referrer_amount_usd": float(self.referrer_amount_usd or 0),
            "membership_days": self.membership_days or 0,
            "membership_period_end": self.membership_period_end.isoformat() if self.membership_period_end else None,
            "membership_plan_code": self.membership_plan_code,
            "referrer_membership_days": self.referrer_membership_days or 0,
            "referrer_membership_plan_code": self.referrer_membership_plan_code,
            "max_uses": self.max_uses,
            "current_uses": self.current_uses or 0,
            "max_uses_per_user": self.max_uses_per_user or 1,
            "require_email_verified": bool(self.require_email_verified),
            "require_referrer": bool(self.require_referrer),
            "starts_at": self.starts_at.isoformat() if self.starts_at else None,
            "ends_at": self.ends_at.isoformat() if self.ends_at else None,
            "is_active": bool(self.is_active),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "partner_external_ref": self.partner_external_ref,
            "parent_promotion_id": str(self.parent_promotion_id) if self.parent_promotion_id else None,
        }


class PromotionRedemption(Base):
    __tablename__ = "promotion_redemptions"
    __table_args__ = (Index("ix_promotion_redemptions_pu", "promotion_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    promotion_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("promotions.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    amount_usd: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    fee_record_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="receiver")
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "promotion_id": str(self.promotion_id),
            "user_id": str(self.user_id),
            "amount_usd": float(self.amount_usd or 0),
            "fee_record_id": str(self.fee_record_id) if self.fee_record_id else None,
            "role": self.role,
            "meta": self.meta or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
