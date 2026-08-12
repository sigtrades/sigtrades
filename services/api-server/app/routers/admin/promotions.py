"""管理员 — 活动/兑换码。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Promotion, PromotionRedemption, User
from app.models.promotion import (
    ALL_PROMO_KINDS,
    CAMPAIGN_KEY_KINDS,
    CODE_KINDS,
    PROMO_KIND_PARTNER_CAMPAIGN,
    PROMO_KIND_REFERRAL,
)
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext

router = APIRouter()


class PromotionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    kind: str
    code: Optional[str] = Field(None, max_length=50)
    amount_usd: float = Field(0, ge=0)
    referrer_amount_usd: float = Field(0, ge=0)
    reward_kind: str = Field("membership_days")
    membership_days: int = Field(0, ge=0)
    membership_plan_code: Optional[str] = None
    referrer_membership_days: int = Field(0, ge=0)
    referrer_membership_plan_code: Optional[str] = None
    max_uses: Optional[int] = Field(None, ge=1)
    max_uses_per_user: int = Field(1, ge=1)
    require_email_verified: bool = False
    require_referrer: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: bool = False


class PromotionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    code: Optional[str] = Field(None, max_length=50)
    amount_usd: Optional[float] = Field(None, ge=0)
    referrer_amount_usd: Optional[float] = Field(None, ge=0)
    reward_kind: Optional[str] = None
    membership_days: Optional[int] = Field(None, ge=0)
    membership_plan_code: Optional[str] = None
    referrer_membership_days: Optional[int] = Field(None, ge=0)
    referrer_membership_plan_code: Optional[str] = None
    max_uses: Optional[int] = Field(None, ge=1)
    max_uses_per_user: Optional[int] = Field(None, ge=1)
    require_email_verified: Optional[bool] = None
    require_referrer: Optional[bool] = None
    starts_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    is_active: Optional[bool] = None


def _normalize_code(raw: Optional[str], kind: str) -> Optional[str]:
    if kind not in CODE_KINDS and kind not in CAMPAIGN_KEY_KINDS:
        return None
    if not raw:
        return None
    normalized = raw.strip().lower()
    if len(normalized) < 4:
        raise HTTPException(status_code=400, detail="兑换码长度至少 4 位")
    return normalized


def _to_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _ensure_only_one_active_per_kind(db: AsyncSession, kind: str, exclude_id: Optional[str] = None):
    if kind not in {"signup_bonus", "referral"}:
        return
    stmt = select(Promotion).where(Promotion.kind == kind, Promotion.is_active.is_(True))
    if exclude_id:
        stmt = stmt.where(Promotion.id != exclude_id)
    for other in (await db.execute(stmt)).scalars().all():
        other.is_active = False


@router.get("")
async def list_promotions(
    kind: Optional[str] = None,
    is_active: Optional[bool] = None,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Promotion).order_by(Promotion.created_at.desc())
    if kind:
        if kind not in ALL_PROMO_KINDS:
            raise HTTPException(status_code=400, detail="kind 参数无效")
        stmt = stmt.where(Promotion.kind == kind)
    if is_active is not None:
        stmt = stmt.where(Promotion.is_active.is_(is_active))
    items = (await db.execute(stmt)).scalars().all()
    return {"success": True, "data": [p.to_dict() for p in items]}


@router.post("")
async def create_promotion(
    data: PromotionCreate,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    if data.kind not in ALL_PROMO_KINDS:
        raise HTTPException(status_code=400, detail="kind 参数无效")

    normalized_code = _normalize_code(data.code, data.kind)
    if data.kind in CODE_KINDS and not normalized_code:
        raise HTTPException(status_code=400, detail=f"{data.kind} 必须设置 code")
    if data.kind == PROMO_KIND_PARTNER_CAMPAIGN and not normalized_code:
        raise HTTPException(status_code=400, detail="partner_campaign 必须设置 campaign_key（填入 code 字段）")
    if data.kind == PROMO_KIND_PARTNER_CAMPAIGN:
        if not data.membership_days or data.membership_days < 1:
            raise HTTPException(status_code=400, detail="partner_campaign 必须设置 membership_days")
        if not (data.membership_plan_code or "").strip():
            raise HTTPException(status_code=400, detail="partner_campaign 必须设置 membership_plan_code")

    max_uses = 1 if data.kind == "code_oneoff" else data.max_uses
    if data.kind == PROMO_KIND_PARTNER_CAMPAIGN:
        max_uses = None  # 模板本身不兑换
    if normalized_code:
        dup = (
            await db.execute(select(Promotion).where(func.lower(Promotion.code) == normalized_code))
        ).scalar_one_or_none()
        if dup:
            raise HTTPException(status_code=409, detail="兑换码已存在，请更换")

    if data.is_active:
        await _ensure_only_one_active_per_kind(db, data.kind)

    require_referrer = data.require_referrer
    if require_referrer is None:
        require_referrer = data.kind == PROMO_KIND_REFERRAL

    promo = Promotion(
        name=data.name.strip(),
        description=(data.description or "").strip() or None,
        kind=data.kind,
        code=normalized_code,
        amount_usd=Decimal(str(data.amount_usd)),
        referrer_amount_usd=Decimal(str(data.referrer_amount_usd)),
        reward_kind=data.reward_kind,
        membership_days=data.membership_days,
        membership_plan_code=data.membership_plan_code,
        referrer_membership_days=data.referrer_membership_days,
        referrer_membership_plan_code=data.referrer_membership_plan_code,
        max_uses=max_uses,
        max_uses_per_user=data.max_uses_per_user,
        require_email_verified=data.require_email_verified,
        require_referrer=bool(require_referrer),
        starts_at=_to_utc(data.starts_at),
        ends_at=_to_utc(data.ends_at),
        is_active=data.is_active,
        created_by="admin",
    )
    db.add(promo)
    await db.commit()
    await db.refresh(promo)
    return {"success": True, "message": "活动已创建", "data": promo.to_dict()}


@router.patch("/{promotion_id}")
async def update_promotion(
    promotion_id: str,
    data: PromotionUpdate,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    promo = (await db.execute(select(Promotion).where(Promotion.id == promotion_id))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="活动不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "code" in update_data:
        new_code = _normalize_code(update_data["code"], promo.kind)
        if (promo.kind in CODE_KINDS or promo.kind in CAMPAIGN_KEY_KINDS) and not new_code:
            raise HTTPException(status_code=400, detail="code 必填")
        if new_code and new_code != promo.code:
            dup = (
                await db.execute(
                    select(Promotion).where(
                        func.lower(Promotion.code) == new_code,
                        Promotion.id != promo.id,
                    )
                )
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail="兑换码已存在")
        update_data["code"] = new_code

    for numeric_key in ("amount_usd", "referrer_amount_usd"):
        if numeric_key in update_data:
            update_data[numeric_key] = Decimal(str(update_data[numeric_key]))
    for tz_key in ("starts_at", "ends_at"):
        if tz_key in update_data:
            update_data[tz_key] = _to_utc(update_data[tz_key])

    if update_data.get("is_active") is True:
        await _ensure_only_one_active_per_kind(db, promo.kind, exclude_id=str(promo.id))

    for k, v in update_data.items():
        setattr(promo, k, v)
    promo.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(promo)
    return {"success": True, "message": "活动已更新", "data": promo.to_dict()}


@router.delete("/{promotion_id}")
async def delete_promotion(
    promotion_id: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    promo = (await db.execute(select(Promotion).where(Promotion.id == promotion_id))).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="活动不存在")
    used = (
        await db.execute(
            select(func.count(PromotionRedemption.id)).where(PromotionRedemption.promotion_id == promo.id)
        )
    ).scalar() or 0
    if used > 0:
        raise HTTPException(status_code=400, detail=f"该活动已有 {used} 次核销记录，不能删除，请停用后保留")
    await db.delete(promo)
    await db.commit()
    return {"success": True, "message": "已删除"}


@router.get("/redemptions")
async def list_redemptions(
    promotion_id: Optional[str] = None,
    user_email: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=200),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(PromotionRedemption, Promotion, User)
        .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
        .join(User, User.id == PromotionRedemption.user_id)
        .order_by(PromotionRedemption.created_at.desc())
    )
    count_stmt = select(func.count()).select_from(PromotionRedemption).join(
        User, User.id == PromotionRedemption.user_id
    )

    if promotion_id:
        stmt = stmt.where(PromotionRedemption.promotion_id == promotion_id)
        count_stmt = count_stmt.where(PromotionRedemption.promotion_id == promotion_id)
    if user_email:
        like = f"%{user_email.strip().lower()}%"
        stmt = stmt.where(func.lower(User.email).like(like))
        count_stmt = count_stmt.where(func.lower(User.email).like(like))

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * limit
    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()

    items = []
    for r, p, u in rows:
        d = r.to_dict()
        meta = r.meta or {}
        d["promotion_name"] = p.name
        d["promotion_kind"] = p.kind
        d["promotion_code"] = p.code
        d["membership_days"] = meta.get("membership_days") or p.membership_days
        d["plan_code"] = meta.get("plan_code") or p.membership_plan_code
        d["user_email"] = u.email
        items.append(d)

    return {"success": True, "data": {"items": items, "total": total, "page": page, "limit": limit}}
