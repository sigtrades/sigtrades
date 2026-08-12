"""管理员 — 支付记录（Stripe / consent 日志 / 统计）。"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import MembershipPlan, PaymentConsentLog, User, UserMembership
from app.routers.admin.deps import verify_admin_token
from app.services.payment_consent_service import mark_consent_paid
from app.services.subscription_payment_analytics import (
    build_subscription_payment_stats,
    resolve_display_status,
    serialize_consent_payment_row,
)
from app.utils.datetime import format_et

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/consents")
async def list_payment_consents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    total = (await db.execute(select(func.count(PaymentConsentLog.id)))).scalar() or 0
    rows = (
        await db.execute(
            select(PaymentConsentLog, User.email)
            .join(User, User.id == PaymentConsentLog.user_id)
            .order_by(PaymentConsentLog.consented_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).all()

    return {
        "success": True,
        "data": {
            "items": [
                {
                    "id": str(c.id),
                    "user_id": str(c.user_id),
                    "user_email": email,
                    "plan_code": c.plan_code,
                    "consented_at": format_et(c.consented_at),
                    "ip_address": c.ip_address,
                    "meta": c.meta or {},
                    "payment_status": (c.meta or {}).get("payment_status") or "pending",
                    "display_status": resolve_display_status(c),
                    "checkout_session_id": (c.meta or {}).get("checkout_session_id"),
                    "amount": (c.meta or {}).get("amount"),
                    "billing_interval": (c.meta or {}).get("billing_interval"),
                }
                for c, email in rows
            ],
            "pagination": {"page": page, "limit": limit, "total": int(total)},
        },
    }


@router.get("/subscription-payments")
async def list_subscription_payments(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    q = (search or "").strip()
    stmt = (
        select(PaymentConsentLog, User.email)
        .join(User, User.id == PaymentConsentLog.user_id)
        .order_by(PaymentConsentLog.consented_at.desc())
    )
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                User.email.ilike(like),
                PaymentConsentLog.plan_code.ilike(like),
                PaymentConsentLog.meta["checkout_session_id"].astext.ilike(like),
            )
        )

    count_stmt = (
        select(func.count(PaymentConsentLog.id))
        .join(User, User.id == PaymentConsentLog.user_id)
    )
    if q:
        like = f"%{q}%"
        count_stmt = count_stmt.where(
            or_(
                User.email.ilike(like),
                PaymentConsentLog.plan_code.ilike(like),
                PaymentConsentLog.meta["checkout_session_id"].astext.ilike(like),
            )
        )
    total = (await db.execute(count_stmt)).scalar() or 0
    rows = (
        await db.execute(stmt.offset((page - 1) * page_size).limit(page_size))
    ).all()

    user_ids = {c.user_id for c, _ in rows}
    paid_users: set = set()
    active_users: set = set()
    membership_by_user: dict = {}
    if user_ids:
        mems = (
            await db.execute(
                select(UserMembership, MembershipPlan)
                .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
                .where(UserMembership.user_id.in_(user_ids))
                .order_by(UserMembership.created_at.desc())
            )
        ).all()
        for m, plan in mems:
            if m.user_id not in membership_by_user:
                membership_by_user[m.user_id] = (m, plan)
            if m.stripe_subscription_id and m.status in ("active", "trialing", "past_due", "canceled"):
                paid_users.add(m.user_id)
            if m.status in ("active", "trialing"):
                active_users.add(m.user_id)

        paid_consents = (
            await db.execute(
                select(PaymentConsentLog.user_id).where(
                    PaymentConsentLog.user_id.in_(user_ids),
                    PaymentConsentLog.meta["payment_status"].astext == "paid",
                )
            )
        ).all()
        for (uid,) in paid_consents:
            paid_users.add(uid)

    items = []
    for consent, email in rows:
        mem_plan = membership_by_user.get(consent.user_id)
        mem = mem_plan[0] if mem_plan else None
        plan = mem_plan[1] if mem_plan else None
        items.append(
            serialize_consent_payment_row(
                consent,
                user_email=email,
                membership=mem,
                plan_name=plan.name if plan else None,
                plan_code=plan.code if plan else consent.plan_code,
                user_has_paid_record=consent.user_id in paid_users,
                user_has_active_membership=consent.user_id in active_users,
            )
        )

    return {
        "success": True,
        "data": items,
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post("/subscription-payments/{consent_id}/resync")
async def resync_subscription_payment(
    consent_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    """手动从 Stripe Checkout Session / Invoice 回写支付与会员状态。"""
    try:
        cid = uuid.UUID(consent_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid consent id") from exc

    consent = (
        await db.execute(select(PaymentConsentLog).where(PaymentConsentLog.id == cid))
    ).scalar_one_or_none()
    if not consent:
        raise HTTPException(status_code=404, detail="consent not found")

    sid = str((consent.meta or {}).get("checkout_session_id") or "").strip()
    if not sid:
        return {"success": True, "data": {"synced": False, "reason": "no_session_id"}}

    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=400, detail="STRIPE_SECRET_KEY not configured")

    import stripe

    from app.routers.stripe_webhook import _as_dict, _sync_subscription

    stripe.api_key = settings.STRIPE_SECRET_KEY

    try:
        if sid.startswith("invoice:"):
            invoice_id = sid.split(":", 1)[1]
            inv = _as_dict(stripe.Invoice.retrieve(invoice_id))
            if inv.get("status") != "paid":
                return {"success": True, "data": {"synced": False, "reason": f"invoice_status={inv.get('status')}"}}
            sub_id = inv.get("subscription")
            if sub_id:
                sub = _as_dict(stripe.Subscription.retrieve(sub_id))
                await _sync_subscription(sub)
            await mark_consent_paid(
                db,
                checkout_session_id=sid,
                consent_id=str(consent.id),
                stripe_subscription_id=str(sub_id) if sub_id else None,
                amount=(float(inv.get("amount_paid") or 0) / 100.0),
                currency=str(inv.get("currency") or "usd"),
                stripe_event="admin.resync.invoice",
            )
            await db.commit()
            return {"success": True, "data": {"synced": True, "reason": "invoice"}}

        if not sid.startswith("cs_"):
            return {"success": True, "data": {"synced": False, "reason": "unsupported_session"}}

        session = _as_dict(stripe.checkout.Session.retrieve(sid))
        if session.get("payment_status") not in ("paid", "no_payment_required") and session.get("status") != "complete":
            return {
                "success": True,
                "data": {
                    "synced": False,
                    "reason": f"session_payment_status={session.get('payment_status')}",
                },
            }
        sub_id = session.get("subscription")
        if sub_id:
            sub = _as_dict(stripe.Subscription.retrieve(sub_id))
            sess_meta = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
            sub_meta = sub.get("metadata") if isinstance(sub.get("metadata"), dict) else {}
            sub["metadata"] = {**(sub_meta or {}), **(sess_meta or {})}
            await _sync_subscription(sub)
        amount_total = session.get("amount_total")
        await mark_consent_paid(
            db,
            checkout_session_id=sid,
            consent_id=str(consent.id),
            stripe_subscription_id=str(sub_id) if sub_id else None,
            amount=(float(amount_total) / 100.0) if amount_total is not None else None,
            currency=str(session.get("currency") or "usd"),
            stripe_event="admin.resync.checkout",
            billing_interval=(session.get("metadata") or {}).get("billing_interval")
            if isinstance(session.get("metadata"), dict)
            else None,
        )
        await db.commit()
        return {"success": True, "data": {"synced": True, "reason": "checkout"}}
    except Exception as exc:  # noqa: BLE001
        logger.warning("resync consent %s failed: %s", consent_id, exc)
        raise HTTPException(status_code=502, detail=f"resync failed: {exc}") from exc


@router.get("/stats")
async def payment_stats(
    days: int = Query(30, ge=1, le=90),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    data = await build_subscription_payment_stats(db, days=days)
    data["stripe_configured"] = bool(settings.STRIPE_SECRET_KEY)
    data["webhook_configured"] = bool(settings.STRIPE_WEBHOOK_SECRET)
    # 兼容旧字段名
    data.setdefault("active_subscriptions", data["active_memberships"])
    return {"success": True, "data": data}
