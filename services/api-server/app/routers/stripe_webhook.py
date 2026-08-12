"""Stripe webhook 骨架：校验签名 + 同步 user_memberships。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import SessionLocal
from app.models import MembershipPlan, User, UserMembership

logger = logging.getLogger(__name__)
# Stripe Dashboard 配置：https://stapi.sigtrades.com/api/v1/payments/stripe/webhook
router = APIRouter(prefix="/api/v1/payments/stripe", tags=["stripe"])

# Checkout / 订阅同步所需事件（Dashboard 或 API 需启用这些，仅 payment_intent.* 不会更新会员）
REQUIRED_WEBHOOK_EVENTS = (
    "checkout.session.completed",
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
    "invoice.paid",
    "invoice.payment_failed",
)


def _as_dict(obj) -> dict:
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


def _subscription_period_end(sub: dict) -> int | None:
    """Stripe 新 API 把 current_period_end 放在 subscription item 上，顶层可能为空。"""
    raw = sub.get("current_period_end")
    if raw:
        return int(raw)
    items = (sub.get("items") or {}).get("data") or []
    if items:
        item_end = items[0].get("current_period_end")
        if item_end:
            return int(item_end)
    return None


def _subscription_price_id(sub: dict) -> str | None:
    items = (sub.get("items") or {}).get("data") or []
    if not items:
        return None
    price = items[0].get("price") or {}
    if isinstance(price, str):
        return price
    return price.get("id")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET 未配置，跳过签名校验（仅 dev）")
        import json
        event = json.loads(body)
    else:
        try:
            import stripe
            stripe.api_key = settings.STRIPE_SECRET_KEY
            event = stripe.Webhook.construct_event(body, sig, settings.STRIPE_WEBHOOK_SECRET)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    etype = event.get("type") if isinstance(event, dict) else event.type
    data_obj = event.get("data", {}).get("object", {}) if isinstance(event, dict) else event.data.object
    data_obj = _as_dict(data_obj)

    if etype in ("customer.subscription.updated", "customer.subscription.created"):
        await _sync_subscription(data_obj)
    elif etype == "customer.subscription.deleted":
        await _cancel_subscription(data_obj)
    elif etype == "checkout.session.completed":
        await _handle_checkout_completed(data_obj)
    elif etype == "invoice.payment_failed":
        await _handle_payment_failed(data_obj)
    elif etype == "invoice.paid":
        await _handle_invoice_paid(data_obj)

    return {"received": True}


async def _sync_subscription(sub: dict) -> None:
    sub = _as_dict(sub)
    customer_id = sub.get("customer")
    sub_id = sub.get("id")
    status = sub.get("status", "active")
    period_end = _subscription_period_end(sub)
    price_id = _subscription_price_id(sub)

    async with SessionLocal() as db:
        user_result = await db.execute(select(User).where(User.stripe_customer_id == customer_id))
        user = user_result.scalar_one_or_none()
        if not user:
            logger.warning("Stripe customer %s 无对应用户", customer_id)
            return

        plan = None
        if price_id:
            plan_result = await db.execute(
                select(MembershipPlan).where(
                    or_(
                        MembershipPlan.stripe_price_id == price_id,
                        MembershipPlan.stripe_price_id_monthly == price_id,
                        MembershipPlan.stripe_price_id_yearly == price_id,
                    )
                )
            )
            plan = plan_result.scalar_one_or_none()
        if price_id and not plan:
            # 未知 price 不再默认升级到 pro：记录告警，保留现有计划，避免配置错误白送权益。
            logger.error("Stripe price %s 无对应计划，保留现有会员计划（不升级）", price_id)

        existing = await db.execute(
            select(UserMembership).where(UserMembership.stripe_subscription_id == sub_id)
        )
        membership = existing.scalar_one_or_none()
        period_dt = datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
        meta = sub.get("metadata") if isinstance(sub.get("metadata"), dict) else {}
        replace_id = str((meta or {}).get("replace_subscription_id") or "").strip()

        is_new = membership is None
        if membership:
            membership.status = status
            membership.period_end = period_dt
            if plan:
                membership.plan_id = plan.id
        else:
            # 月↔年切换：新 Checkout 订阅替换旧订阅，挂到原会员行
            replaced = None
            if replace_id and plan:
                replaced = (
                    await db.execute(
                        select(UserMembership).where(
                            UserMembership.user_id == user.id,
                            UserMembership.stripe_subscription_id == replace_id,
                        )
                    )
                ).scalar_one_or_none()
            if replaced and plan:
                replaced.plan_id = plan.id
                replaced.status = status
                replaced.period_end = period_dt
                replaced.stripe_subscription_id = sub_id
                membership = replaced
            # 赠送/试用（无 stripe_subscription_id）转正：挂到同一行，避免并存两条 active Pro
            gift = None
            if membership is None:
                gift = (
                    await db.execute(
                        select(UserMembership)
                        .where(
                            UserMembership.user_id == user.id,
                            UserMembership.status.in_(("active", "trialing")),
                            UserMembership.stripe_subscription_id.is_(None),
                        )
                        .order_by(UserMembership.period_end.desc().nullslast())
                    )
                ).scalars().first()
            if gift and plan:
                gift.plan_id = plan.id
                gift.status = status
                gift.period_end = period_dt
                gift.stripe_subscription_id = sub_id
                membership = gift
            elif membership is None:
                fallback_plan_id = None
                if plan:
                    fallback_plan_id = plan.id
                elif user.memberships:
                    fallback_plan_id = user.memberships[0].plan_id
                else:
                    free_result = await db.execute(
                        select(MembershipPlan).where(MembershipPlan.code == "free")
                    )
                    free_plan = free_result.scalar_one_or_none()
                    fallback_plan_id = free_plan.id if free_plan else None
                if fallback_plan_id is None:
                    logger.error("无法确定会员计划，跳过创建 membership（sub=%s）", sub_id)
                    return
                membership = UserMembership(
                    user_id=user.id,
                    plan_id=fallback_plan_id,
                    status=status,
                    period_end=period_dt,
                    stripe_subscription_id=sub_id,
                )
                db.add(membership)

            # 作废同用户其他仍 active 的会员行
            others = (
                await db.execute(
                    select(UserMembership).where(
                        UserMembership.user_id == user.id,
                        UserMembership.id != membership.id,
                        UserMembership.status.in_(("active", "trialing")),
                    )
                )
            ).scalars().all()
            for row in others:
                row.status = "expired"

        if is_new and plan and status in ("active", "trialing") and not replace_id:
            from app.services.email_service import send_subscription_email
            import asyncio
            await asyncio.to_thread(send_subscription_email, user.email, plan.name, user.language)
        await db.commit()

        # 月↔年切换：取消被替换的旧 Stripe 订阅，避免双扣费
        if replace_id and replace_id != sub_id and status in ("active", "trialing"):
            try:
                import stripe

                stripe.api_key = settings.STRIPE_SECRET_KEY
                stripe.Subscription.cancel(replace_id)
                logger.info("canceled replaced subscription %s -> %s", replace_id, sub_id)
            except Exception as e:  # noqa: BLE001
                logger.warning("cancel replaced subscription %s failed: %s", replace_id, e)


async def _cancel_subscription(sub: dict) -> None:
    sub = _as_dict(sub)
    sub_id = sub.get("id")
    period_end = _subscription_period_end(sub)
    async with SessionLocal() as db:
        result = await db.execute(
            select(UserMembership).where(UserMembership.stripe_subscription_id == sub_id)
        )
        membership = result.scalar_one_or_none()
        if not membership:
            return
        # 取消但保留权益到账期结束（period_end），到期后由 scheduler 降级为 free。
        membership.status = "canceled"
        period_dt = datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
        if period_dt:
            membership.period_end = period_dt
        if membership.period_end is None or membership.period_end <= datetime.now(timezone.utc):
            # 已无账期可宽限：立即降级到 free，并收回自动下单。
            free = await db.execute(select(MembershipPlan).where(MembershipPlan.code == "free"))
            free_plan = free.scalar_one_or_none()
            if free_plan:
                membership.plan_id = free_plan.id
                membership.status = "expired"
                from app.services.plan_downgrade import demote_auto_trade_rules

                await demote_auto_trade_rules(db, membership.user_id)
        await db.commit()


async def _handle_checkout_completed(session: dict) -> None:
    session = _as_dict(session)
    customer_id = session.get("customer")
    sub_id = session.get("subscription")
    sess_meta = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
    if not customer_id or not sub_id:
        return
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        sub = _as_dict(stripe.Subscription.retrieve(sub_id))
        # Checkout session metadata 优先带上 replace_subscription_id
        sub_meta = sub.get("metadata") if isinstance(sub.get("metadata"), dict) else {}
        merged_meta = {**(sub_meta or {}), **(sess_meta or {})}
        if merged_meta:
            sub["metadata"] = merged_meta
        await _sync_subscription(sub)
    except Exception as e:
        logger.warning("checkout.session.completed sync failed: %s", e)

    # 回写扣费同意 → 已支付（后台支付状态）
    try:
        from app.services.payment_consent_service import mark_consent_paid

        amount_total = session.get("amount_total")
        amount = (float(amount_total) / 100.0) if amount_total is not None else None
        async with SessionLocal() as db:
            await mark_consent_paid(
                db,
                checkout_session_id=session.get("id"),
                consent_id=(sess_meta or {}).get("payment_consent_id"),
                stripe_subscription_id=str(sub_id) if sub_id else None,
                amount=amount,
                currency=str(session.get("currency") or "usd"),
                stripe_event="checkout.session.completed",
                billing_interval=(sess_meta or {}).get("billing_interval"),
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("mark consent paid after checkout failed: %s", e)


async def _handle_payment_failed(invoice: dict) -> None:
    invoice = _as_dict(invoice)
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    async with SessionLocal() as db:
        result = await db.execute(
            select(UserMembership).where(UserMembership.stripe_subscription_id == sub_id)
        )
        membership = result.scalar_one_or_none()
        if membership:
            membership.status = "past_due"
            await db.commit()
            logger.warning("Stripe subscription past_due: %s", sub_id)


async def _handle_invoice_paid(invoice: dict) -> None:
    invoice = _as_dict(invoice)
    sub_id = invoice.get("subscription")
    if not sub_id:
        return
    sub_dict: dict = {}
    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY
        sub_dict = _as_dict(stripe.Subscription.retrieve(sub_id))
        await _sync_subscription(sub_dict)
    except Exception as e:
        logger.warning("invoice.paid sync failed: %s", e)

    # 续费发票记一条已支付，便于后台统计
    billing_reason = str(invoice.get("billing_reason") or "")
    if billing_reason in ("subscription_cycle", "subscription_update", "subscription_create"):
        try:
            from app.services.payment_consent_service import record_invoice_payment
            from app.services.stripe_service import billing_interval_for_price

            customer_id = invoice.get("customer")
            amount_paid = invoice.get("amount_paid")
            amount = (float(amount_paid) / 100.0) if amount_paid is not None else 0.0
            async with SessionLocal() as db:
                user = (
                    await db.execute(select(User).where(User.stripe_customer_id == customer_id))
                ).scalar_one_or_none()
                if not user:
                    return
                price_id = _subscription_price_id(sub_dict) if sub_dict else None
                plan = None
                if price_id:
                    plan = (
                        await db.execute(
                            select(MembershipPlan).where(
                                or_(
                                    MembershipPlan.stripe_price_id == price_id,
                                    MembershipPlan.stripe_price_id_monthly == price_id,
                                    MembershipPlan.stripe_price_id_yearly == price_id,
                                )
                            )
                        )
                    ).scalar_one_or_none()
                plan_code = plan.code if plan else "pro"
                interval = billing_interval_for_price(plan, price_id) if plan else None
                await record_invoice_payment(
                    db,
                    user_id=user.id,
                    plan_code=plan_code,
                    invoice_id=str(invoice.get("id") or ""),
                    amount=amount,
                    currency=str(invoice.get("currency") or "usd"),
                    stripe_subscription_id=str(sub_id),
                    billing_interval=interval,
                )
                await db.commit()
        except Exception as e:  # noqa: BLE001
            logger.warning("record invoice payment failed: %s", e)
