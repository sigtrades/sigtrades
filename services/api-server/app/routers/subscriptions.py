"""Stripe 订阅：Checkout + Customer Portal + 账单查询。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_current_user, get_verified_user
from app.models import User
from app.services.entitlements import get_active_membership, get_active_plan
from app.services.stripe_service import (
    create_checkout_session,
    create_portal_session,
    get_default_payment_method,
    list_invoices,
    resolve_subscription_billing_interval,
)
from app.utils.datetime import format_et

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


class CheckoutRequest(BaseModel):
    plan_code: str = "pro"
    billing_interval: str = "monthly"
    success_url: HttpUrl
    cancel_url: HttpUrl
    payment_consent: bool = False


class PortalRequest(BaseModel):
    return_url: HttpUrl


class ChangeBillingIntervalRequest(BaseModel):
    billing_interval: str  # monthly | yearly
    success_url: HttpUrl
    cancel_url: HttpUrl


class PreviewBillingIntervalRequest(BaseModel):
    billing_interval: str  # monthly | yearly


def _days_remaining(period_end: Optional[datetime]) -> Optional[int]:
    if not period_end:
        return None
    now = datetime.now(timezone.utc)
    if period_end <= now:
        return 0
    # 不足 24h 时 .days 会变成 0，至少显示 1 天剩余
    seconds = (period_end - now).total_seconds()
    return max(1, int(seconds // 86400) + (1 if seconds % 86400 else 0))


def _billing_cycle_label(status: str, stripe_subscription_id: Optional[str]) -> str:
    if status == "trialing":
        return "trial"
    if not stripe_subscription_id:
        return "gift"
    return "subscription"


_PLAN_RANK = {"free": 0, "starter": 1, "pro": 2}


@router.post("/checkout-session")
async def checkout_session(
    req: CheckoutRequest,
    request: Request,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.BILLING_CHECKOUT_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="billing_checkout_disabled",
        )

    # 同档或更低不可 checkout（含赠送/试用 Pro）：避免 Stripe 账期覆盖剩余赠送天数
    target = (req.plan_code or "").strip().lower()
    current_plan = await get_active_plan(db, user.id)
    current = (current_plan.code if current_plan else "free").strip().lower()
    # 同档不可新建 Checkout（含赠送/付费 Pro）；不再提供月付↔年付切换
    if _PLAN_RANK.get(target, 0) <= _PLAN_RANK.get(current, 0):
        raise HTTPException(status_code=400, detail="already_on_plan")

    try:
        url = await create_checkout_session(
            db,
            user,
            req.plan_code,
            str(req.success_url),
            str(req.cancel_url),
            billing_interval=req.billing_interval,
            consent=req.payment_consent,
            ip_address=request.client.host if request.client else None,
        )
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — Stripe SDK / 网络错误需对前端可见
        raise HTTPException(status_code=502, detail=f"stripe checkout failed: {e}") from e
    return {"url": url}


@router.post("/portal")
async def customer_portal(
    req: PortalRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        url = await create_portal_session(db, user, str(req.return_url))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"url": url}


@router.post("/preview-billing-interval")
async def preview_billing_interval(
    req: PreviewBillingIntervalRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """已停用：不再支持月付↔年付切换（补差价难算）。"""
    _ = (req, user, db)
    raise HTTPException(status_code=400, detail="billing_interval_switch_disabled")


@router.post("/change-billing-interval")
async def change_billing_interval(
    req: ChangeBillingIntervalRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """已停用：不再支持月付↔年付切换（补差价难算）。"""
    _ = (req, user, db)
    raise HTTPException(status_code=400, detail="billing_interval_switch_disabled")


@router.get("/status")
async def subscription_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await get_active_plan(db, user.id)
    membership = await get_active_membership(db, user.id)
    status = membership.status if membership else ("free" if plan is None else "active")
    period_end = membership.period_end if membership else None
    billing_cycle = _billing_cycle_label(
        status,
        membership.stripe_subscription_id if membership else None,
    )
    billing_interval = None
    if membership and membership.stripe_subscription_id and plan and settings.STRIPE_SECRET_KEY:
        try:
            billing_interval = await resolve_subscription_billing_interval(
                membership.stripe_subscription_id,
                plan,
            )
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).warning(
                "resolve billing_interval failed sub=%s: %s",
                membership.stripe_subscription_id,
                exc,
            )
            billing_interval = None
    return {
        "plan_code": plan.code if plan else "free",
        "plan_name": plan.name if plan else "Free",
        "status": status,
        "period_end": format_et(period_end) if period_end else None,
        "billing_cycle": billing_cycle,
        "billing_interval": billing_interval,
        "days_remaining": _days_remaining(period_end),
        "stripe_configured": bool(settings.STRIPE_SECRET_KEY),
        "has_stripe_customer": bool(user.stripe_customer_id),
    }


@router.get("/payment-method")
async def subscription_payment_method(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not settings.STRIPE_SECRET_KEY:
        return {"configured": False, "method": None}
    try:
        method = await get_default_payment_method(db, user)
    except ValueError:
        return {"configured": False, "method": None}
    except Exception as e:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("payment-method fetch failed: %s", e)
        return {"configured": True, "method": None}
    return {"configured": True, "method": method}


@router.get("/invoices")
async def subscription_invoices(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
):
    if not settings.STRIPE_SECRET_KEY or not user.stripe_customer_id:
        return {"items": []}
    try:
        items = await list_invoices(db, user, year=year, month=month)
    except ValueError:
        return {"items": []}
    except Exception as e:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).warning("invoices fetch failed: %s", e)
        return {"items": []}
    return {
        "items": [
            {
                **item,
                "date": format_et(datetime.fromtimestamp(item["date"], tz=timezone.utc)) if item.get("date") else None,
            }
            for item in items
        ],
    }
