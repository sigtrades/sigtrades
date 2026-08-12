"""管理员 — 用户订阅。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MembershipPlan, PaymentConsentLog, Promotion, PromotionRedemption, User, UserMembership
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext
from app.services.subscription_payment_analytics import membership_payment_label
from app.utils.datetime import format_et


def _consent_amount_map(consents: list[PaymentConsentLog]) -> dict[str, dict]:
    """按 stripe_subscription_id / user_id 取最近一笔已支付金额。"""
    by_sub: dict[str, dict] = {}
    by_user: dict[str, dict] = {}
    for c in consents:
        meta = dict(c.meta or {})
        if str(meta.get("payment_status") or "") != "paid":
            continue
        try:
            amount = float(meta.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if amount <= 0:
            continue
        interval = str(meta.get("billing_interval") or meta.get("billing_cycle") or "").strip().lower()
        payload = {
            "amount": amount,
            "currency": str(meta.get("currency") or "usd"),
            "billing_interval": interval if interval in ("monthly", "yearly") else None,
            "consented_at": c.consented_at,
        }
        sid = str(meta.get("stripe_subscription_id") or "").strip()
        if sid and sid not in by_sub:
            by_sub[sid] = payload
        uid = str(c.user_id)
        # consents 按时间倒序传入时，首次即为最近一笔
        if uid not in by_user:
            by_user[uid] = payload
    return {"by_sub": by_sub, "by_user": by_user}


def _resolve_payment_amount(
    *,
    stripe_subscription_id: str | None,
    user_id: str,
    plan: MembershipPlan,
    amount_maps: dict,
) -> dict:
    if not (stripe_subscription_id or "").strip():
        return {
            "payment_amount": None,
            "payment_amount_usd": None,
            "billing_interval": None,
            "currency": "usd",
        }
    sid = str(stripe_subscription_id).strip()
    hit = amount_maps["by_sub"].get(sid) or amount_maps["by_user"].get(user_id)
    if hit and hit.get("amount"):
        return {
            "payment_amount": float(hit["amount"]),
            "payment_amount_usd": float(hit["amount"]),
            "billing_interval": hit.get("billing_interval"),
            "currency": hit.get("currency") or "usd",
        }
    # 无支付流水时回退套餐标价（默认月付）
    monthly = float(plan.price_monthly or 0) if plan.price_monthly is not None else None
    yearly = float(plan.price_yearly or 0) if plan.price_yearly is not None else None
    amount = monthly if monthly and monthly > 0 else yearly
    interval = "monthly" if monthly and monthly > 0 else ("yearly" if yearly and yearly > 0 else None)
    return {
        "payment_amount": amount,
        "payment_amount_usd": amount,
        "billing_interval": interval,
        "currency": "usd",
    }

router = APIRouter()


def _membership_source_label(
    *,
    stripe_subscription_id: str | None,
    redeem: dict | None,
) -> str:
    if (stripe_subscription_id or "").strip():
        return "Stripe"
    if redeem:
        days = redeem.get("membership_days")
        code = redeem.get("promo_code") or ""
        name = redeem.get("promo_name") or "兑换码"
        if days:
            return f"兑换 · {name} · {days}天"
        if code:
            return f"兑换 · {code}"
        return "兑换码"
    return "后台/其他"


class GrantSubscription(BaseModel):
    user_id: str
    plan_code: str
    status: str = "active"
    days: Optional[int] = Field(None, ge=1, le=3650)


class BatchGrantBody(BaseModel):
    user_ids: list[str] = Field(default_factory=list)
    plan_code: str
    days: int = Field(30, ge=1, le=3650)


class ExtendSubscriptionBody(BaseModel):
    days: int = Field(..., ge=1, le=3650)


@router.get("")
async def admin_subscriptions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    count_stmt = select(func.count(UserMembership.id))
    if status:
        count_stmt = count_stmt.where(UserMembership.status == status)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(UserMembership, User.email, MembershipPlan)
        .join(User, User.id == UserMembership.user_id)
        .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
        .order_by(UserMembership.created_at.desc())
    )
    if status:
        stmt = stmt.where(UserMembership.status == status)

    result = await db.execute(stmt.offset(offset).limit(limit))
    rows = result.all()
    mem_ids = [str(m.id) for m, *_ in rows]
    user_ids = [m.user_id for m, *_ in rows]
    redeem_by_mem: dict[str, dict] = {}
    if mem_ids:
        # meta.membership_id 在兑换时写入
        red_rows = (
            await db.execute(
                select(PromotionRedemption, Promotion)
                .join(Promotion, Promotion.id == PromotionRedemption.promotion_id)
                .where(PromotionRedemption.meta["membership_id"].astext.in_(mem_ids))
            )
        ).all()
        for red, promo in red_rows:
            mid = str((red.meta or {}).get("membership_id") or "")
            if not mid or mid in redeem_by_mem:
                continue
            redeem_by_mem[mid] = {
                "promo_code": promo.code,
                "promo_name": promo.name,
                "membership_days": (red.meta or {}).get("membership_days") or promo.membership_days,
            }

    amount_maps: dict = {"by_sub": {}, "by_user": {}}
    if user_ids:
        consents = (
            await db.execute(
                select(PaymentConsentLog)
                .where(PaymentConsentLog.user_id.in_(user_ids))
                .order_by(PaymentConsentLog.consented_at.desc())
            )
        ).scalars().all()
        amount_maps = _consent_amount_map(list(consents))

    items = []
    for m, email, plan in rows:
        pay_amt = _resolve_payment_amount(
            stripe_subscription_id=m.stripe_subscription_id,
            user_id=str(m.user_id),
            plan=plan,
            amount_maps=amount_maps,
        )
        items.append(
            {
                "id": str(m.id),
                "user_id": str(m.user_id),
                "user_email": email,
                "plan_id": str(m.plan_id),
                "plan_code": plan.code,
                "plan_name": plan.name,
                "status": m.status,
                "stripe_subscription_id": m.stripe_subscription_id,
                "period_end": format_et(m.period_end),
                "created_at": format_et(m.created_at),
                "source": _membership_source_label(
                    stripe_subscription_id=m.stripe_subscription_id,
                    redeem=redeem_by_mem.get(str(m.id)),
                ),
                "redeem_code": (redeem_by_mem.get(str(m.id)) or {}).get("promo_code"),
                **membership_payment_label(
                    status=m.status,
                    stripe_subscription_id=m.stripe_subscription_id,
                    has_redeem=str(m.id) in redeem_by_mem,
                ),
                **pay_amt,
            }
        )

    return {
        "success": True,
        "data": {
            "items": items,
            "pagination": {"page": page, "limit": limit, "total": int(total)},
        },
    }


@router.post("/grant")
async def grant_subscription(
    req: GrantSubscription,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    plan = await db.execute(select(MembershipPlan).where(MembershipPlan.code == req.plan_code))
    p = plan.scalar_one_or_none()
    if not p:
        raise HTTPException(status_code=404, detail="plan not found")
    period_end = None
    if req.days:
        period_end = datetime.now(timezone.utc) + timedelta(days=req.days)
    db.add(
        UserMembership(
            user_id=uuid.UUID(req.user_id),
            plan_id=p.id,
            status=req.status,
            period_end=period_end,
        )
    )
    await db.commit()
    return {"success": True}


@router.post("/batch-grant")
async def batch_grant_subscription(
    body: BatchGrantBody,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    if not body.user_ids:
        raise HTTPException(status_code=400, detail="user_ids required")
    plan = (await db.execute(select(MembershipPlan).where(MembershipPlan.code == body.plan_code))).scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="plan not found")
    period_end = datetime.now(timezone.utc) + timedelta(days=body.days)
    created = 0
    for uid_str in body.user_ids:
        try:
            uid = uuid.UUID(uid_str)
        except ValueError:
            continue
        user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
        if not user:
            continue
        db.add(
            UserMembership(
                user_id=uid,
                plan_id=plan.id,
                status="active",
                period_end=period_end,
            )
        )
        created += 1
    await db.commit()
    return {"success": True, "data": {"granted_count": created, "user_count": len(body.user_ids)}}


@router.post("/{membership_id}/extend")
async def extend_subscription(
    membership_id: str,
    body: ExtendSubscriptionBody,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(membership_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid membership id")
    m = (await db.execute(select(UserMembership).where(UserMembership.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="not found")
    now = datetime.now(timezone.utc)
    base = m.period_end if m.period_end and m.period_end > now else now
    m.period_end = base + timedelta(days=body.days)
    if m.status in ("canceled", "expired"):
        m.status = "active"
    await db.commit()
    return {
        "success": True,
        "data": {"status": m.status, "period_end": format_et(m.period_end)},
    }


@router.post("/{membership_id}/cancel")
async def cancel_subscription(
    membership_id: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(membership_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid membership id")
    m = (await db.execute(select(UserMembership).where(UserMembership.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="not found")
    m.status = "canceled"
    await db.commit()
    return {"success": True, "data": {"status": m.status}}


@router.post("/{membership_id}/reactivate")
async def reactivate_subscription(
    membership_id: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        mid = uuid.UUID(membership_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid membership id")
    m = (await db.execute(select(UserMembership).where(UserMembership.id == mid))).scalar_one_or_none()
    if not m:
        raise HTTPException(status_code=404, detail="not found")
    m.status = "active"
    await db.commit()
    return {"success": True, "data": {"status": m.status}}
