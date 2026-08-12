"""Stripe Checkout + Customer Portal（简化版）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import MembershipPlan, PaymentConsentLog, User

logger = logging.getLogger(__name__)


def _ensure_stripe() -> None:
    if not settings.STRIPE_SECRET_KEY:
        raise ValueError("STRIPE_SECRET_KEY not configured")
    stripe.api_key = settings.STRIPE_SECRET_KEY


async def _stripe_call(fn, /, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def _stripe_dict(obj) -> dict:
    """新版 stripe SDK 的 StripeObject 无可靠 .get()，统一转 dict。"""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    try:
        return dict(obj)
    except Exception:
        return {}


def _payment_method_summary(pm: dict | None) -> Optional[dict]:
    """支持 card / Link 等；Checkout 用 Link 付时 type=link，无 card.last4。"""
    if not pm:
        return None
    if isinstance(pm, str):
        return None
    ptype = str(pm.get("type") or "").strip().lower()
    billing = pm.get("billing_details") if isinstance(pm.get("billing_details"), dict) else {}

    if ptype == "card" or (isinstance(pm.get("card"), dict) and pm["card"].get("last4")):
        card = pm.get("card") if isinstance(pm.get("card"), dict) else {}
        last4 = card.get("last4")
        if not last4:
            return None
        brand = card.get("brand") or "card"
        return {
            "id": pm.get("id"),
            "type": "card",
            "brand": brand,
            "last4": last4,
            "exp_month": card.get("exp_month"),
            "exp_year": card.get("exp_year"),
            "label": f"{str(brand).upper()} •••• {last4}",
        }

    if ptype == "link":
        link = pm.get("link") if isinstance(pm.get("link"), dict) else {}
        email = link.get("email") or billing.get("email")
        return {
            "id": pm.get("id"),
            "type": "link",
            "brand": "Link",
            "last4": None,
            "email": email,
            "label": f"Link · {email}" if email else "Stripe Link",
        }

    if ptype:
        return {
            "id": pm.get("id"),
            "type": ptype,
            "brand": ptype.replace("_", " "),
            "last4": None,
            "label": ptype.replace("_", " ").title(),
        }
    return None


# 兼容旧调用名
_card_summary = _payment_method_summary


async def ensure_customer(db: AsyncSession, user: User) -> str:
    _ensure_stripe()
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = _stripe_dict(
        await _stripe_call(
            stripe.Customer.create,
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
    )
    user.stripe_customer_id = customer["id"]
    await db.commit()
    await db.refresh(user)
    return customer["id"]


async def create_checkout_session(
    db: AsyncSession,
    user: User,
    plan_code: str,
    success_url: str,
    cancel_url: str,
    *,
    billing_interval: str = "monthly",
    consent: bool = True,
    ip_address: Optional[str] = None,
) -> str:
    _ensure_stripe()
    if not consent:
        raise ValueError("payment consent required")

    result = await db.execute(select(MembershipPlan).where(MembershipPlan.code == plan_code))
    plan = result.scalar_one_or_none()
    if not plan:
        raise ValueError(f"plan not found: {plan_code}")
    if not bool(getattr(plan, "is_active", True)):
        raise ValueError(f"plan is disabled: {plan_code}")
    price_id = plan.resolve_stripe_price_id(billing_interval)
    if not price_id:
        raise ValueError(f"plan has no valid stripe price for billing interval: {billing_interval}")

    interval = (billing_interval or "monthly").strip().lower()
    if interval in ("yearly", "annual", "year"):
        amount = float(plan.price_yearly or 0)
    else:
        amount = float(plan.price_monthly or 0)

    consent = PaymentConsentLog(
        user_id=user.id,
        plan_code=plan_code,
        ip_address=ip_address,
        meta={
            "success_url": success_url,
            "payment_status": "pending",
            "billing_interval": interval if interval in ("monthly", "yearly") else "monthly",
            "amount": amount,
            "currency": "usd",
        },
    )
    db.add(consent)
    await db.flush()

    customer_id = await ensure_customer(db, user)
    session = _stripe_dict(
        await _stripe_call(
            stripe.checkout.Session.create,
            mode="subscription",
            customer=customer_id,
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                "user_id": str(user.id),
                "plan_code": plan_code,
                "billing_interval": billing_interval,
                "payment_consent_id": str(consent.id),
            },
        )
    )
    session_id = session.get("id")
    if session_id:
        from sqlalchemy.orm.attributes import flag_modified

        meta = dict(consent.meta or {})
        meta["checkout_session_id"] = session_id
        consent.meta = meta
        flag_modified(consent, "meta")
        await db.flush()
    return session["url"]


async def create_portal_session(db: AsyncSession, user: User, return_url: str) -> str:
    _ensure_stripe()
    customer_id = await ensure_customer(db, user)
    session = _stripe_dict(
        await _stripe_call(
            stripe.billing_portal.Session.create,
            customer=customer_id,
            return_url=return_url,
        )
    )
    return session["url"]


def billing_interval_for_price(plan: MembershipPlan, price_id: Optional[str]) -> Optional[str]:
    """根据 Stripe price id 判断月付/年付。"""
    if not price_id or not plan:
        return None
    pid = str(price_id).strip()
    yearly = (plan.stripe_price_id_yearly or "").strip()
    monthly = (plan.stripe_price_id_monthly or plan.stripe_price_id or "").strip()
    if yearly and pid == yearly:
        return "yearly"
    if monthly and pid == monthly:
        return "monthly"
    return None


async def get_active_subscription_price_id(stripe_subscription_id: str) -> Optional[str]:
    _ensure_stripe()
    sub = _stripe_dict(
        await _stripe_call(
            stripe.Subscription.retrieve,
            stripe_subscription_id,
            expand=["items.data.price"],
        )
    )
    items = ((sub.get("items") or {}).get("data") or [])
    if not items:
        return None
    price = items[0].get("price")
    if isinstance(price, str):
        return price
    if isinstance(price, dict):
        return price.get("id")
    return None


async def resolve_subscription_billing_interval(
    stripe_subscription_id: str,
    plan: MembershipPlan,
) -> Optional[str]:
    """先按计划配置的 price id 映射；对不上时回退 Stripe recurring.interval。"""
    _ensure_stripe()
    sub = _stripe_dict(
        await _stripe_call(
            stripe.Subscription.retrieve,
            stripe_subscription_id,
            expand=["items.data.price"],
        )
    )
    items = ((sub.get("items") or {}).get("data") or [])
    if not items:
        return None
    price = items[0].get("price")
    price_id = None
    recurring_interval = None
    if isinstance(price, str):
        price_id = price
    elif isinstance(price, dict):
        price_id = price.get("id")
        recurring = price.get("recurring") if isinstance(price.get("recurring"), dict) else {}
        recurring_interval = recurring.get("interval")
    mapped = billing_interval_for_price(plan, price_id)
    if mapped:
        return mapped
    if recurring_interval == "year":
        return "yearly"
    if recurring_interval == "month":
        return "monthly"
    return None


def _subscription_period_end_ts(sub: dict) -> Optional[int]:
    raw = sub.get("current_period_end")
    if raw:
        return int(raw)
    items = ((sub.get("items") or {}).get("data") or [])
    if items:
        item_end = items[0].get("current_period_end")
        if item_end:
            return int(item_end)
    return None


async def _load_interval_switch_context(
    db: AsyncSession,
    user: User,
    *,
    billing_interval: str,
):
    """校验并加载月↔年切换上下文；年付期内禁止切回月付。"""
    from datetime import datetime, timezone

    from app.services.entitlements import get_active_membership, get_active_plan

    interval = (billing_interval or "").strip().lower()
    if interval not in ("monthly", "yearly"):
        raise ValueError("billing_interval must be monthly or yearly")

    membership = await get_active_membership(db, user.id)
    if not membership or not membership.stripe_subscription_id:
        raise ValueError("no_active_stripe_subscription")
    plan = await get_active_plan(db, user.id)
    if not plan or plan.code == "free":
        raise ValueError("plan not found")

    new_price = plan.resolve_stripe_price_id(interval)
    if not new_price:
        raise ValueError(f"plan has no valid stripe price for billing interval: {interval}")

    sub_id = membership.stripe_subscription_id
    sub = _stripe_dict(
        await _stripe_call(
            stripe.Subscription.retrieve,
            sub_id,
            expand=["items.data.price"],
        )
    )
    items = ((sub.get("items") or {}).get("data") or [])
    if not items:
        raise ValueError("subscription has no items")
    item_id = items[0].get("id")
    if not item_id:
        raise ValueError("subscription item missing id")

    current_price = items[0].get("price")
    current_price_id = None
    recurring_interval = None
    if isinstance(current_price, dict):
        current_price_id = current_price.get("id")
        recurring = current_price.get("recurring") if isinstance(current_price.get("recurring"), dict) else {}
        recurring_interval = recurring.get("interval")
    else:
        current_price_id = current_price
    current_interval = billing_interval_for_price(plan, current_price_id)
    if not current_interval:
        if recurring_interval == "year":
            current_interval = "yearly"
        elif recurring_interval == "month":
            current_interval = "monthly"

    # 年付期内不可切回月付；到期后（period_end 已过）才允许
    if current_interval == "yearly" and interval == "monthly":
        period_end_ts = _subscription_period_end_ts(sub)
        if not period_end_ts and membership.period_end:
            pe = membership.period_end
            if pe.tzinfo is None:
                pe = pe.replace(tzinfo=timezone.utc)
            period_end_ts = int(pe.timestamp())
        now_ts = datetime.now(timezone.utc).timestamp()
        if not period_end_ts or period_end_ts > now_ts:
            raise ValueError("yearly_to_monthly_locked")

    return {
        "interval": interval,
        "membership": membership,
        "plan": plan,
        "sub_id": sub_id,
        "sub": sub,
        "item_id": item_id,
        "current_price_id": current_price_id,
        "current_interval": current_interval,
        "new_price": new_price,
    }


async def preview_billing_interval_change(
    db: AsyncSession,
    user: User,
    *,
    billing_interval: str,
) -> dict:
    """预览月→年补差价（不扣款），供前端确认提示。"""
    _ensure_stripe()
    ctx = await _load_interval_switch_context(db, user, billing_interval=billing_interval)
    interval = ctx["interval"]
    sub_id = ctx["sub_id"]
    item_id = ctx["item_id"]
    new_price = ctx["new_price"]
    current_interval = ctx["current_interval"]

    if ctx["current_price_id"] == new_price:
        return {
            "ok": True,
            "unchanged": True,
            "current_interval": current_interval,
            "billing_interval": interval,
            "amount_due": 0,
            "amount_due_usd": 0.0,
            "currency": "usd",
            "subscription_id": sub_id,
        }

    customer_id = await ensure_customer(db, user)
    preview = None
    try:
        preview = _stripe_dict(
            await _stripe_call(
                stripe.Invoice.create_preview,
                customer=customer_id,
                subscription=sub_id,
                subscription_details={
                    "items": [{"id": item_id, "price": new_price}],
                    "proration_behavior": "create_prorations",
                },
            )
        )
    except Exception:
        # 兼容旧 SDK：Invoice.upcoming
        preview = _stripe_dict(
            await _stripe_call(
                stripe.Invoice.upcoming,
                customer=customer_id,
                subscription=sub_id,
                subscription_items=[{"id": item_id, "price": new_price}],
                subscription_proration_behavior="create_prorations",
            )
        )

    amount_due = int(preview.get("amount_due") or 0)
    currency = str(preview.get("currency") or "usd").lower()
    return {
        "ok": True,
        "unchanged": False,
        "current_interval": current_interval,
        "billing_interval": interval,
        "amount_due": amount_due,
        "amount_due_usd": round(amount_due / 100.0, 2),
        "currency": currency,
        "subscription_id": sub_id,
        "requires_payment": amount_due > 0,
    }


async def create_billing_interval_checkout(
    db: AsyncSession,
    user: User,
    *,
    billing_interval: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    """月付→年付：补差价但不自动扣款，强制跳转 Stripe Hosted Invoice 支付页。"""
    from datetime import datetime, timezone

    _ensure_stripe()
    ctx = await _load_interval_switch_context(db, user, billing_interval=billing_interval)
    interval = ctx["interval"]
    membership = ctx["membership"]
    plan = ctx["plan"]
    sub_id = ctx["sub_id"]
    sub = ctx["sub"]
    item_id = ctx["item_id"]
    new_price = ctx["new_price"]

    if ctx["current_price_id"] == new_price:
        return {
            "ok": True,
            "unchanged": True,
            "paid": True,
            "billing_interval": interval,
            "subscription_id": sub_id,
            "url": None,
        }

    meta = sub.get("metadata") if isinstance(sub.get("metadata"), dict) else {}
    # default_incomplete：不自动用已存卡扣款，必须走账单页确认支付
    updated = _stripe_dict(
        await _stripe_call(
            stripe.Subscription.modify,
            sub_id,
            items=[{"id": item_id, "price": new_price}],
            proration_behavior="always_invoice",
            payment_behavior="default_incomplete",
            metadata={
                **meta,
                "user_id": str(user.id),
                "plan_code": plan.code,
                "billing_interval": interval,
            },
            expand=["latest_invoice"],
        )
    )

    invoice = updated.get("latest_invoice")
    if isinstance(invoice, str):
        invoice = _stripe_dict(await _stripe_call(stripe.Invoice.retrieve, invoice))
    else:
        invoice = _stripe_dict(invoice)

    # draft 账单需 finalize 后才有 hosted_invoice_url
    inv_id = invoice.get("id")
    if inv_id and str(invoice.get("status") or "") == "draft":
        invoice = _stripe_dict(await _stripe_call(stripe.Invoice.finalize_invoice, inv_id))

    amount_due = int(invoice.get("amount_due") or 0)
    amount_paid = int(invoice.get("amount_paid") or 0)
    inv_status = str(invoice.get("status") or "")
    period_end_ts = _subscription_period_end_ts(updated)

    # 无需补差：订阅已生效
    if amount_due <= 0 and inv_status in ("paid", "void", ""):
        if period_end_ts:
            membership.period_end = datetime.fromtimestamp(period_end_ts, tz=timezone.utc)
        if updated.get("status") in ("active", "trialing"):
            membership.status = updated["status"]
        await db.flush()
        return {
            "ok": True,
            "unchanged": False,
            "paid": True,
            "billing_interval": interval,
            "amount_due": 0,
            "amount_due_usd": 0.0,
            "subscription_id": sub_id,
            "url": None,
        }

    _ = (success_url, cancel_url)
    pay_url = invoice.get("hosted_invoice_url")
    if not pay_url and inv_id:
        # 再拉一次，确保有支付链接
        invoice = _stripe_dict(await _stripe_call(stripe.Invoice.retrieve, inv_id))
        pay_url = invoice.get("hosted_invoice_url")
    if not pay_url:
        raise ValueError("proration invoice missing payment url")

    return {
        "ok": True,
        "unchanged": False,
        "paid": False,
        "billing_interval": interval,
        "amount_due": amount_due or amount_paid,
        "amount_due_usd": round((amount_due or amount_paid) / 100.0, 2),
        "currency": str(invoice.get("currency") or "usd"),
        "subscription_id": sub_id,
        "invoice_id": invoice.get("id"),
        "url": pay_url,
    }


async def _retrieve_payment_method(pm_id: str) -> Optional[dict]:
    try:
        return _stripe_dict(await _stripe_call(stripe.PaymentMethod.retrieve, pm_id))
    except Exception as exc:
        logger.warning("retrieve payment_method %s failed: %s", pm_id, exc)
        return None


async def get_default_payment_method(db: AsyncSession, user: User) -> Optional[dict]:
    """优先客户默认支付方式；Checkout/Link 常挂在订阅上，再回退已挂载 PM。"""
    _ensure_stripe()
    if not user.stripe_customer_id:
        return None
    customer_id = user.stripe_customer_id
    customer = _stripe_dict(
        await _stripe_call(
            stripe.Customer.retrieve,
            customer_id,
            expand=["invoice_settings.default_payment_method"],
        )
    )
    invoice_settings = customer.get("invoice_settings") or {}
    pm = invoice_settings.get("default_payment_method")
    if isinstance(pm, str):
        pm = await _retrieve_payment_method(pm)
    summary = _payment_method_summary(pm if isinstance(pm, dict) else None)
    if summary:
        return summary

    # 订阅上的 default_payment_method（Checkout / Link 常见）
    found_pm_id: Optional[str] = None
    subs = _stripe_dict(
        await _stripe_call(
            stripe.Subscription.list,
            customer=customer_id,
            status="all",
            limit=5,
            expand=["data.default_payment_method"],
        )
    )
    for sub in subs.get("data") or []:
        if not isinstance(sub, dict):
            sub = _stripe_dict(sub)
        if sub.get("status") not in ("active", "trialing", "past_due"):
            continue
        spm = sub.get("default_payment_method")
        if isinstance(spm, str):
            found_pm_id = spm
            spm = await _retrieve_payment_method(spm)
        elif spm is not None:
            spm = _stripe_dict(spm)
            found_pm_id = spm.get("id")
        summary = _payment_method_summary(spm)
        if summary:
            # 回写客户默认，避免下次仍为空
            if found_pm_id and not invoice_settings.get("default_payment_method"):
                try:
                    await _stripe_call(
                        stripe.Customer.modify,
                        customer_id,
                        invoice_settings={"default_payment_method": found_pm_id},
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.info("sync customer default PM skipped: %s", exc)
            return summary

    # 客户已挂载的支付方式（含 Link，不能只查 type=card）
    try:
        pms = _stripe_dict(
            await _stripe_call(
                stripe.Customer.list_payment_methods,
                customer_id,
                limit=10,
            )
        )
    except Exception:
        pms = _stripe_dict(
            await _stripe_call(
                stripe.PaymentMethod.list,
                customer=customer_id,
                type="card",
                limit=5,
            )
        )
    for item in pms.get("data") or []:
        summary = _payment_method_summary(item if isinstance(item, dict) else _stripe_dict(item))
        if summary:
            return summary
    return None


async def list_invoices(
    db: AsyncSession,
    user: User,
    *,
    year: int,
    month: int,
    limit: int = 20,
) -> list[dict]:
    _ensure_stripe()
    if not user.stripe_customer_id:
        return []
    from calendar import monthrange
    from datetime import datetime, timezone

    start = datetime(year, month, 1, tzinfo=timezone.utc)
    last_day = monthrange(year, month)[1]
    end = datetime(year, month, last_day, 23, 59, 59, tzinfo=timezone.utc)
    invoices = _stripe_dict(
        await _stripe_call(
            stripe.Invoice.list,
            customer=user.stripe_customer_id,
            limit=limit,
            created={"gte": int(start.timestamp()), "lte": int(end.timestamp())},
        )
    )
    out = []
    for raw in invoices.get("data") or []:
        inv = raw if isinstance(raw, dict) else _stripe_dict(raw)
        lines = ((inv.get("lines") or {}).get("data") or [])
        first_line = lines[0] if lines else {}
        if not isinstance(first_line, dict):
            first_line = _stripe_dict(first_line)
        desc = first_line.get("description") or inv.get("description") or "Subscription"
        out.append({
            "id": inv.get("id"),
            "date": inv.get("created"),
            "description": desc,
            "status": inv.get("status"),
            "amount": (inv.get("amount_paid") or 0) / 100,
            "currency": (inv.get("currency") or "usd").upper(),
            "hosted_invoice_url": inv.get("hosted_invoice_url"),
        })
    return out
