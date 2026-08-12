"""合作发码 + 用户兑换：membership_days / 绝对 period_end / plan 发放。"""

from __future__ import annotations

import logging
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Union
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models import MembershipPlan, Promotion, PromotionRedemption, User, UserMembership
from app.models.promotion import (
    PROMO_KIND_CODE_ONEOFF,
    PROMO_KIND_PARTNER_CAMPAIGN,
)

logger = logging.getLogger(__name__)

DEFAULT_CAMPAIGN_KEY = "sunnyquant_pro_gift"
DEFAULT_CAMPAIGN_PAID_KEY = "sunnyquant_pro_paid"
DEFAULT_CAMPAIGN_MEMBERSHIP_DAYS = 1  # 模板占位；合作发码以 period_end 为准
DEFAULT_CAMPAIGN_PAID_MEMBERSHIP_DAYS = 30  # 模板占位；合作发码以 period_end 为准
DEFAULT_CAMPAIGN_PLAN_CODE = "pro"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_redeem_code(raw: str) -> str:
    code = (raw or "").strip().lower()
    if len(code) < 4:
        raise HTTPException(status_code=400, detail="兑换码无效")
    return code


def _parse_period_end(raw: Union[str, datetime, None]) -> datetime:
    if isinstance(raw, datetime):
        dt = raw
    else:
        s = (raw or "").strip()
        if not s:
            raise HTTPException(status_code=400, detail="period_end required")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="period_end invalid ISO datetime") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt


def period_end_from_partner_ref(ref: str) -> Optional[datetime]:
    """从 external_ref「sq_membership:<uuid>:<iso8601>」解析 SQ 到期日。"""
    raw = (ref or "").strip()
    parts = raw.split(":", 2)
    if len(parts) < 3 or parts[0] != "sq_membership":
        return None
    try:
        return _parse_period_end(parts[2])
    except HTTPException:
        return None


async def backfill_partner_gift_period_ends(db: AsyncSession) -> int:
    """旧合作码按天数发放；用 external_ref 里的 SQ 到期日回填 membership / 码上的绝对到期。"""
    from app.models import UserMembership

    promos = (
        await db.execute(
            select(Promotion).where(
                Promotion.partner_external_ref.isnot(None),
                Promotion.kind == PROMO_KIND_CODE_ONEOFF,
            )
        )
    ).scalars().all()
    updated = 0
    for promo in promos:
        absolute = period_end_from_partner_ref(promo.partner_external_ref or "")
        if not absolute or absolute <= _now():
            continue
        promo_changed = False
        if promo.membership_period_end != absolute:
            promo.membership_period_end = absolute
            promo_changed = True
        if promo.ends_at != absolute:
            promo.ends_at = absolute
            promo_changed = True
        if promo_changed:
            updated += 1

        reds = (
            await db.execute(
                select(PromotionRedemption).where(PromotionRedemption.promotion_id == promo.id)
            )
        ).scalars().all()
        for red in reds:
            mid = (red.meta or {}).get("membership_id")
            if not mid:
                continue
            try:
                mem_uuid = uuid.UUID(str(mid))
            except ValueError:
                continue
            mem = (
                await db.execute(select(UserMembership).where(UserMembership.id == mem_uuid))
            ).scalar_one_or_none()
            if not mem:
                continue
            if mem.period_end != absolute:
                mem.period_end = absolute
                mem.status = "active"
                updated += 1
                meta = dict(red.meta or {})
                meta["membership_period_end"] = absolute.isoformat()
                meta["membership_days"] = _days_until(absolute)
                red.meta = meta

    if updated:
        await db.commit()
        logger.info("backfill_partner_gift_period_ends updated=%s", updated)
    return updated


def _days_until(period_end: datetime, *, now: Optional[datetime] = None) -> int:
    base = now or _now()
    seconds = (period_end - base).total_seconds()
    return max(1, int(math.ceil(seconds / 86400.0)))


def redeem_url_for_code(code: str) -> str:
    base = (settings.FRONTEND_URL or "http://127.0.0.1:5173").rstrip("/")
    return f"{base}/redeem?code={quote(code, safe='')}"


def _mint_response(promo: Promotion, *, idempotent: bool) -> Dict[str, Any]:
    return {
        "code": promo.code,
        "redeem_url": redeem_url_for_code(promo.code or ""),
        "plan_code": promo.membership_plan_code,
        "membership_days": promo.membership_days or 0,
        "period_end": promo.membership_period_end.isoformat() if promo.membership_period_end else None,
        "ends_at": promo.ends_at.isoformat() if promo.ends_at else None,
        "idempotent": idempotent,
    }


async def get_active_partner_campaign(
    db: AsyncSession,
    campaign_key: str,
) -> Promotion:
    key = (campaign_key or "").strip().lower()
    if not key:
        raise HTTPException(status_code=400, detail="campaign_key required")
    promo = (
        await db.execute(
            select(Promotion).where(
                Promotion.kind == PROMO_KIND_PARTNER_CAMPAIGN,
                func.lower(Promotion.code) == key,
            )
        )
    ).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="合作活动未配置")
    if not promo.is_active:
        raise HTTPException(status_code=403, detail="合作活动未启用")
    now = _now()
    if promo.starts_at and promo.starts_at > now:
        raise HTTPException(status_code=403, detail="合作活动尚未开始")
    if promo.ends_at and promo.ends_at <= now:
        raise HTTPException(status_code=403, detail="合作活动已结束")
    if not (promo.membership_plan_code or "").strip():
        raise HTTPException(status_code=500, detail="合作活动未配置 membership_plan_code")
    return promo


async def mint_partner_code(
    db: AsyncSession,
    *,
    campaign_key: str,
    external_ref: str,
    partner: str = "sunnyquant",
    period_end: Union[str, datetime, None] = None,
) -> Dict[str, Any]:
    """按活动模板发一次性码；会员到期日严格等于调用方传入的 period_end（SQ 到期日）。"""
    ref = (external_ref or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="external_ref required")
    if len(ref) > 128:
        raise HTTPException(status_code=400, detail="external_ref too long")

    absolute_end = _parse_period_end(period_end)
    now = _now()
    if absolute_end <= now:
        raise HTTPException(status_code=400, detail="period_end must be in the future")

    existing = (
        await db.execute(select(Promotion).where(Promotion.partner_external_ref == ref))
    ).scalar_one_or_none()
    if existing and existing.code and existing.is_active:
        return _mint_response(existing, idempotent=True)
    if existing and not existing.is_active:
        # 已停用的一次性码：清掉 external_ref，允许同 ref 重新发码
        existing.partner_external_ref = None
        await db.flush()

    campaign = await get_active_partner_campaign(db, campaign_key)
    # 高熵一次性码
    for _ in range(8):
        code = secrets.token_urlsafe(18).lower().replace("-", "").replace("_", "")[:24]
        if len(code) < 16:
            continue
        dup = (
            await db.execute(select(Promotion.id).where(func.lower(Promotion.code) == code))
        ).scalar_one_or_none()
        if not dup:
            break
    else:
        raise HTTPException(status_code=500, detail="无法生成唯一兑换码")

    display_days = _days_until(absolute_end, now=now)
    oneoff = Promotion(
        name=f"{campaign.name} · gift",
        description=f"partner={partner}; campaign={campaign.code}; ref={ref}",
        kind=PROMO_KIND_CODE_ONEOFF,
        code=code,
        reward_kind="membership_days",
        amount_usd=Decimal("0"),
        referrer_amount_usd=Decimal("0"),
        membership_days=display_days,
        membership_period_end=absolute_end,
        membership_plan_code=(campaign.membership_plan_code or "").strip().lower(),
        max_uses=1,
        current_uses=0,
        max_uses_per_user=1,
        require_email_verified=bool(campaign.require_email_verified),
        require_referrer=False,
        starts_at=campaign.starts_at or now,
        ends_at=absolute_end,
        is_active=True,
        created_by=f"partner:{partner}",
        partner_external_ref=ref,
        parent_promotion_id=campaign.id,
    )
    db.add(oneoff)
    await db.flush()
    # 模型列 default=False；显式再写一次，避免落库成停用导致「兑换码不存在/已停用」
    if not oneoff.is_active:
        oneoff.is_active = True
    await db.commit()
    await db.refresh(oneoff)
    logger.info(
        "minted partner code campaign=%s ref=%s code=%s period_end=%s active=%s…",
        campaign.code,
        ref,
        code[:6],
        absolute_end.isoformat(),
        oneoff.is_active,
    )
    return _mint_response(oneoff, idempotent=False)


async def _find_active_membership(db: AsyncSession, user_id: uuid.UUID) -> Optional[UserMembership]:
    return (
        await db.execute(
            select(UserMembership)
            .options(selectinload(UserMembership.plan))
            .where(
                UserMembership.user_id == user_id,
                UserMembership.status.in_(("active", "trialing")),
            )
            .order_by(UserMembership.period_end.desc().nullslast())
        )
    ).scalars().first()


async def _grant_membership_until(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    plan_code: str,
    period_end: datetime,
) -> UserMembership:
    """发放会员，period_end 严格等于传入值（与 SQ 到期对齐）。"""
    plan = (
        await db.execute(select(MembershipPlan).where(MembershipPlan.code == plan_code))
    ).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=500, detail=f"plan {plan_code} not found")

    now = _now()
    if period_end <= now:
        raise HTTPException(status_code=400, detail="会员到期日已过")

    active = await _find_active_membership(db, user_id)

    if active:
        was_free = active.plan is None or (active.plan and active.plan.code == "free")
        active.plan_id = plan.id
        active.status = "active"
        active.period_end = period_end
        if was_free:
            active.stripe_subscription_id = None
        await db.flush()
        await _expire_superseded_memberships(db, user_id, keep_id=active.id)
        return active

    mem = UserMembership(
        user_id=user_id,
        plan_id=plan.id,
        status="active",
        period_end=period_end,
    )
    db.add(mem)
    await db.flush()
    await _expire_superseded_memberships(db, user_id, keep_id=mem.id)
    return mem


async def _grant_membership_days(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    plan_code: str,
    days: int,
) -> UserMembership:
    plan = (
        await db.execute(select(MembershipPlan).where(MembershipPlan.code == plan_code))
    ).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=500, detail=f"plan {plan_code} not found")

    now = _now()
    period_end = now + timedelta(days=max(1, int(days)))

    # 若已有未过期同档或更高权益，在现有 period_end 上叠加天数
    active = await _find_active_membership(db, user_id)

    if active and active.period_end and active.period_end > now:
        base_end = active.period_end
        # 切换到目标套餐（赠送 pro）
        active.plan_id = plan.id
        active.status = "active"
        active.period_end = base_end + timedelta(days=max(1, int(days)))
        await db.flush()
        await _expire_superseded_memberships(db, user_id, keep_id=active.id)
        return active

    # 注册留下的 free（period_end 为空）直接升级，避免并存两条 active
    if active and (active.period_end is None or (active.plan and active.plan.code == "free")):
        active.plan_id = plan.id
        active.status = "active"
        active.period_end = period_end
        active.stripe_subscription_id = None
        await db.flush()
        await _expire_superseded_memberships(db, user_id, keep_id=active.id)
        return active

    mem = UserMembership(
        user_id=user_id,
        plan_id=plan.id,
        status="active",
        period_end=period_end,
    )
    db.add(mem)
    await db.flush()
    await _expire_superseded_memberships(db, user_id, keep_id=mem.id)
    return mem


async def _expire_superseded_memberships(
    db: AsyncSession,
    user_id,
    *,
    keep_id,
) -> None:
    """赠送/升级后，作废同用户其他仍 active 的旧会员行（尤其是无到期日的 free）。"""
    others = (
        await db.execute(
            select(UserMembership).where(
                UserMembership.user_id == user_id,
                UserMembership.id != keep_id,
                UserMembership.status.in_(("active", "trialing")),
            )
        )
    ).scalars().all()
    for row in others:
        row.status = "expired"


async def _prior_redemption_for_user(
    db: AsyncSession,
    *,
    promo: Promotion,
    user_id: uuid.UUID,
) -> Optional[PromotionRedemption]:
    return (
        await db.execute(
            select(PromotionRedemption)
            .where(
                PromotionRedemption.promotion_id == promo.id,
                PromotionRedemption.user_id == user_id,
            )
            .order_by(PromotionRedemption.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _already_redeemed_payload(
    db: AsyncSession,
    *,
    promo: Promotion,
    redemption: PromotionRedemption,
    user_id: uuid.UUID,
) -> Dict[str, Any]:
    meta = redemption.meta if isinstance(redemption.meta, dict) else {}
    plan_code = (
        str(meta.get("plan_code") or promo.membership_plan_code or "").strip().lower() or None
    )
    period_end = meta.get("membership_period_end")
    if not period_end and promo.membership_period_end is not None:
        period_end = promo.membership_period_end.isoformat()
    membership_days = meta.get("membership_days")
    mid = meta.get("membership_id")
    # 若会员行仍在，优先用当前 period_end（付费转正后可能已变）
    if mid:
        try:
            mem_id = uuid.UUID(str(mid))
        except ValueError:
            mem_id = None
        if mem_id:
            mem = (
                await db.execute(select(UserMembership).where(UserMembership.id == mem_id))
            ).scalar_one_or_none()
            if mem and mem.period_end is not None:
                period_end = mem.period_end.isoformat()
                if mem.user_id == user_id:
                    pe = mem.period_end
                    if pe.tzinfo is None:
                        pe = pe.replace(tzinfo=timezone.utc)
                    secs = (pe - _now()).total_seconds()
                    membership_days = max(0, int(math.ceil(secs / 86400.0))) if secs > 0 else 0
    if membership_days is None and period_end:
        try:
            pe = _parse_period_end(period_end)
            secs = (pe - _now()).total_seconds()
            membership_days = max(0, int(math.ceil(secs / 86400.0))) if secs > 0 else 0
        except HTTPException:
            membership_days = None
    return {
        "ok": True,
        "already_redeemed": True,
        "status": "already_redeemed",
        "plan_code": plan_code,
        "membership_days": int(membership_days) if membership_days is not None else None,
        "period_end": period_end,
        "redeemed_at": redemption.created_at.isoformat() if redemption.created_at else None,
        "code": promo.code,
    }


async def redeem_code_for_user(
    db: AsyncSession,
    user: User,
    raw_code: str,
) -> Dict[str, Any]:
    code = _normalize_redeem_code(raw_code)
    promo = (
        await db.execute(
            select(Promotion).where(
                func.lower(Promotion.code) == code,
                Promotion.kind == PROMO_KIND_CODE_ONEOFF,
            )
        )
    ).scalar_one_or_none()
    if not promo:
        # 也允许公开/定向码兑换
        promo = (
            await db.execute(
                select(Promotion).where(func.lower(Promotion.code) == code)
            )
        ).scalar_one_or_none()
    if not promo or promo.kind == PROMO_KIND_PARTNER_CAMPAIGN:
        raise HTTPException(status_code=404, detail="兑换码不存在")

    # 本人已兑过：即使码已停用/用完，也返回兑换详情（避免只看到「已停用」）
    prior = await _prior_redemption_for_user(db, promo=promo, user_id=user.id)
    if prior:
        return await _already_redeemed_payload(db, promo=promo, redemption=prior, user_id=user.id)

    if not promo.is_active:
        if promo.max_uses is not None and int(promo.current_uses or 0) >= int(promo.max_uses):
            raise HTTPException(status_code=409, detail="兑换码已用完")
        raise HTTPException(status_code=400, detail="兑换码已停用")
    now = _now()
    if promo.starts_at and promo.starts_at > now:
        raise HTTPException(status_code=400, detail="兑换码尚未生效")
    if promo.ends_at and promo.ends_at <= now:
        raise HTTPException(status_code=400, detail="兑换码已过期")
    if promo.require_email_verified and not user.email_verified:
        raise HTTPException(status_code=400, detail="请先验证邮箱后再兑换")

    if promo.max_uses is not None and int(promo.current_uses or 0) >= int(promo.max_uses):
        raise HTTPException(status_code=409, detail="兑换码已用完")

    plan_code = (promo.membership_plan_code or "").strip().lower()
    if not plan_code:
        raise HTTPException(status_code=400, detail="该兑换码未配置会员权益")

    absolute = promo.membership_period_end
    if absolute is not None:
        absolute = _parse_period_end(absolute)
        if absolute <= now:
            raise HTTPException(status_code=400, detail="兑换码对应会员已到期")
        membership = await _grant_membership_until(
            db, user.id, plan_code=plan_code, period_end=absolute
        )
        days = _days_until(absolute, now=now)
    else:
        days = int(promo.membership_days or 0)
        if days < 1:
            raise HTTPException(status_code=400, detail="该兑换码未配置会员权益")
        membership = await _grant_membership_days(db, user.id, plan_code=plan_code, days=days)

    promo.current_uses = int(promo.current_uses or 0) + 1
    if promo.max_uses is not None and promo.current_uses >= promo.max_uses:
        promo.is_active = False

    db.add(
        PromotionRedemption(
            promotion_id=promo.id,
            user_id=user.id,
            amount_usd=Decimal("0"),
            role="receiver",
            meta={
                "plan_code": plan_code,
                "membership_days": days,
                "membership_period_end": membership.period_end.isoformat() if membership.period_end else None,
                "membership_id": str(membership.id),
            },
        )
    )
    await db.commit()
    return {
        "ok": True,
        "already_redeemed": False,
        "status": "redeemed",
        "plan_code": plan_code,
        "membership_days": days,
        "period_end": membership.period_end.isoformat() if membership.period_end else None,
        "redeemed_at": _now().isoformat(),
        "code": promo.code,
    }


async def _ensure_partner_campaign(
    db: AsyncSession,
    *,
    key: str,
    name: str,
    description: str,
    days: int,
) -> None:
    existing = (
        await db.execute(
            select(Promotion).where(
                Promotion.kind == PROMO_KIND_PARTNER_CAMPAIGN,
                func.lower(Promotion.code) == key.lower(),
            )
        )
    ).scalar_one_or_none()
    if existing:
        changed = False
        if int(existing.membership_days or 0) != int(days):
            existing.membership_days = int(days)
            changed = True
        plan = (existing.membership_plan_code or "").strip().lower()
        if plan != DEFAULT_CAMPAIGN_PLAN_CODE:
            existing.membership_plan_code = DEFAULT_CAMPAIGN_PLAN_CODE
            changed = True
        if not existing.is_active:
            existing.is_active = True
            changed = True
        if changed:
            await db.commit()
            logger.info("Updated partner campaign %s days=%s", key, days)
        return
    db.add(
        Promotion(
            name=name,
            description=description,
            kind=PROMO_KIND_PARTNER_CAMPAIGN,
            code=key,
            reward_kind="membership_days",
            membership_days=int(days),
            membership_plan_code=DEFAULT_CAMPAIGN_PLAN_CODE,
            max_uses=None,
            max_uses_per_user=1,
            is_active=True,
            created_by="system",
        )
    )
    await db.commit()
    logger.info("Seeded partner campaign %s days=%s", key, days)


async def ensure_default_sunnyquant_campaign(db: AsyncSession) -> None:
    """启动时确保赠送 + 付费两个合作模板存在（发码时以 SQ 传入的 period_end 为准）。"""
    await _ensure_partner_campaign(
        db,
        key=DEFAULT_CAMPAIGN_KEY,
        name="SunnyQuant 赠送会员",
        description="SQ 后台赠送/试用 Pro → SigTrades Pro（到期日与 SQ 严格对齐，需用户自行兑换）",
        days=DEFAULT_CAMPAIGN_MEMBERSHIP_DAYS,
    )
    await _ensure_partner_campaign(
        db,
        key=DEFAULT_CAMPAIGN_PAID_KEY,
        name="SunnyQuant 付费会员",
        description="SQ Stripe/Paddle 付费 Pro → SigTrades Pro（到期日与 SQ 严格对齐，需用户自行兑换）",
        days=DEFAULT_CAMPAIGN_PAID_MEMBERSHIP_DAYS,
    )
