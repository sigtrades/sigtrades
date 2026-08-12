"""PaymentConsentLog 支付状态回写（Checkout / Invoice）。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import PaymentConsentLog

logger = logging.getLogger(__name__)


def _merge_meta(consent: PaymentConsentLog, patch: dict[str, Any]) -> None:
    meta = dict(consent.meta or {})
    meta.update(patch)
    consent.meta = meta
    flag_modified(consent, "meta")


async def find_consent_by_session(
    db: AsyncSession,
    *,
    checkout_session_id: Optional[str] = None,
    consent_id: Optional[str] = None,
) -> Optional[PaymentConsentLog]:
    if consent_id:
        try:
            cid = uuid.UUID(str(consent_id))
        except ValueError:
            cid = None
        if cid:
            row = (
                await db.execute(select(PaymentConsentLog).where(PaymentConsentLog.id == cid))
            ).scalar_one_or_none()
            if row:
                return row
    sid = (checkout_session_id or "").strip()
    if not sid:
        return None
    rows = (
        await db.execute(
            select(PaymentConsentLog)
            .where(PaymentConsentLog.meta["checkout_session_id"].astext == sid)
            .order_by(PaymentConsentLog.consented_at.desc())
            .limit(1)
        )
    ).scalars().all()
    return rows[0] if rows else None


async def mark_consent_paid(
    db: AsyncSession,
    *,
    checkout_session_id: Optional[str] = None,
    consent_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    amount: Optional[float] = None,
    currency: str = "usd",
    stripe_event: str = "checkout.session.completed",
    billing_interval: Optional[str] = None,
) -> Optional[PaymentConsentLog]:
    consent = await find_consent_by_session(
        db,
        checkout_session_id=checkout_session_id,
        consent_id=consent_id,
    )
    if not consent:
        logger.info(
            "no payment consent to mark paid (session=%s consent=%s)",
            checkout_session_id,
            consent_id,
        )
        return None

    patch: dict[str, Any] = {
        "payment_status": "paid",
        "paid_at": datetime.now(timezone.utc).isoformat(),
        "stripe_event": stripe_event,
    }
    if stripe_subscription_id:
        patch["stripe_subscription_id"] = stripe_subscription_id
    if amount is not None:
        patch["amount"] = float(amount)
    if currency:
        patch["currency"] = currency
    if billing_interval:
        patch["billing_interval"] = billing_interval
    if checkout_session_id:
        patch["checkout_session_id"] = checkout_session_id
    _merge_meta(consent, patch)
    return consent


async def mark_consent_failed(
    db: AsyncSession,
    *,
    checkout_session_id: Optional[str] = None,
    stripe_subscription_id: Optional[str] = None,
    stripe_event: str = "invoice.payment_failed",
) -> Optional[PaymentConsentLog]:
    consent = await find_consent_by_session(db, checkout_session_id=checkout_session_id)
    if not consent and stripe_subscription_id:
        rows = (
            await db.execute(
                select(PaymentConsentLog)
                .where(
                    PaymentConsentLog.meta["stripe_subscription_id"].astext
                    == stripe_subscription_id
                )
                .order_by(PaymentConsentLog.consented_at.desc())
                .limit(1)
            )
        ).scalars().all()
        consent = rows[0] if rows else None
    if not consent:
        return None
    _merge_meta(
        consent,
        {
            "payment_status": "failed",
            "stripe_event": stripe_event,
        },
    )
    return consent


async def record_invoice_payment(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    plan_code: str,
    invoice_id: str,
    amount: float,
    currency: str = "usd",
    stripe_subscription_id: Optional[str] = None,
    billing_interval: Optional[str] = None,
) -> PaymentConsentLog:
    """续费发票：写入一条 paid 记录便于后台统计。"""
    sid = f"invoice:{invoice_id}"
    existing = await find_consent_by_session(db, checkout_session_id=sid)
    if existing:
        await mark_consent_paid(
            db,
            checkout_session_id=sid,
            stripe_subscription_id=stripe_subscription_id,
            amount=amount,
            currency=currency,
            stripe_event="invoice.paid",
            billing_interval=billing_interval,
        )
        return existing

    consent = PaymentConsentLog(
        user_id=user_id,
        plan_code=plan_code,
        meta={
            "checkout_session_id": sid,
            "payment_status": "paid",
            "paid_at": datetime.now(timezone.utc).isoformat(),
            "stripe_event": "invoice.paid",
            "auto_renewal": True,
            "amount": float(amount),
            "currency": currency or "usd",
            "stripe_subscription_id": stripe_subscription_id,
            "billing_interval": billing_interval,
        },
    )
    db.add(consent)
    return consent
