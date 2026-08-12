"""订阅付费统计（PaymentConsentLog.meta + 有效会员）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PaymentConsentLog, UserMembership
from app.utils.datetime import APP_TZ, ensure_utc, et_day_start_utc, to_et


def _meta(consent: PaymentConsentLog) -> dict:
    return dict(consent.meta or {})


def _pay_status(consent: PaymentConsentLog) -> str:
    return str(_meta(consent).get("payment_status") or "pending")


def _session_id(consent: PaymentConsentLog) -> str:
    return str(_meta(consent).get("checkout_session_id") or "").strip()


def resolve_payment_kind(consent: PaymentConsentLog) -> str:
    """首开 initial | 续费 renewal | 升级 upgrade | 未支付意向 intent。"""
    extra = _meta(consent)
    sid = _session_id(consent)
    stripe_event = str(extra.get("stripe_event") or "")

    if extra.get("auto_renewal") or sid.startswith("invoice:") or stripe_event == "invoice.paid":
        return "renewal"
    if sid.startswith(("upgrade:", "upgrade_applied:", "portal_cycle:")):
        return "upgrade"
    if _pay_status(consent) == "paid":
        return "initial"
    if sid.startswith("cs_"):
        return "initial"
    return "intent"


def resolve_display_status(
    consent: PaymentConsentLog,
    *,
    user_has_paid_record: bool = False,
    user_has_active_membership: bool = False,
) -> str:
    """管理后台展示：paid | pending_sync | abandoned | failed | superseded。"""
    raw = _pay_status(consent)
    if raw == "paid":
        return "paid"
    if raw in ("superseded", "abandoned"):
        return raw
    if raw == "failed" or str(_meta(consent).get("stripe_event") or "") == "invoice.payment_failed":
        return "failed"

    kind = resolve_payment_kind(consent)
    sid = _session_id(consent)

    if kind == "renewal":
        if sid.startswith("invoice:"):
            return "pending_sync"
        return "failed"

    if kind == "intent":
        return "abandoned"

    if sid.startswith("cs_"):
        if user_has_paid_record or user_has_active_membership:
            return "abandoned"
        return "pending_sync"

    return "abandoned"


def _is_actionable_pending(consent: PaymentConsentLog) -> bool:
    if _pay_status(consent) == "paid":
        return False
    sid = _session_id(consent)
    if not sid:
        return False
    if sid.startswith("invoice:"):
        return True
    return sid.startswith("cs_") and not sid.startswith(
        ("portal_cycle:", "upgrade:", "upgrade_applied:")
    )


def _paid_at_dt(consent: PaymentConsentLog) -> Optional[datetime]:
    extra = _meta(consent)
    raw = extra.get("paid_at")
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return ensure_utc(dt)
        except ValueError:
            pass
    if _pay_status(consent) == "paid" and consent.consented_at:
        return ensure_utc(consent.consented_at)
    return None


def _paid_day_et(consent: PaymentConsentLog) -> Optional[date]:
    if _pay_status(consent) != "paid":
        return None
    dt = _paid_at_dt(consent)
    if not dt:
        return None
    et = to_et(dt)
    return et.date() if et else None


def _membership_is_valid(status: str, period_end: Optional[datetime], *, now: datetime) -> bool:
    if status not in ("active", "trialing", "canceled", "past_due"):
        return False
    if status in ("active", "trialing", "past_due"):
        if period_end is None:
            return True
        return ensure_utc(period_end) > now
    # canceled：保留到账期结束
    if status == "canceled" and period_end is not None:
        return ensure_utc(period_end) > now
    return False


def membership_payment_label(
    *,
    status: str,
    stripe_subscription_id: Optional[str],
    has_redeem: bool,
) -> dict[str, str]:
    """会员行付费标记：paid/gift/redeem/trial。"""
    if status == "trialing":
        return {"payment_status": "trial", "payment_status_label": "试用"}
    if (stripe_subscription_id or "").strip():
        return {"payment_status": "paid", "payment_status_label": "付费成功"}
    if has_redeem:
        return {"payment_status": "redeem", "payment_status_label": "兑换"}
    if status in ("active", "canceled", "past_due"):
        return {"payment_status": "gift", "payment_status_label": "赠送"}
    return {"payment_status": "none", "payment_status_label": "—"}


async def build_subscription_payment_stats(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    mem_rows = (
        await db.execute(
            select(
                UserMembership.status,
                UserMembership.period_end,
                UserMembership.stripe_subscription_id,
            )
        )
    ).all()

    active_memberships = 0
    paid_memberships = 0
    gift_memberships = 0
    trial_memberships = 0
    stripe_subscriptions = 0
    for status, period_end, stripe_id in mem_rows:
        if stripe_id:
            stripe_subscriptions += 1
        if not _membership_is_valid(status, period_end, now=now):
            continue
        active_memberships += 1
        if status == "trialing":
            trial_memberships += 1
        elif stripe_id:
            paid_memberships += 1
        else:
            gift_memberships += 1

    all_consents = (await db.execute(select(PaymentConsentLog))).scalars().all()
    paid_rows = [c for c in all_consents if _pay_status(c) == "paid"]
    pending_sync_rows = [c for c in all_consents if _is_actionable_pending(c)]
    unpaid_intent_count = max(0, len(all_consents) - len(paid_rows) - len(pending_sync_rows))
    total_paid_amount = sum(float(_meta(c).get("amount") or 0) for c in paid_rows)

    today_start = et_day_start_utc(now)
    today_end = today_start + timedelta(days=1)
    today_paid_rows = []
    for c in paid_rows:
        dt = _paid_at_dt(c)
        if dt and today_start <= dt < today_end:
            today_paid_rows.append(c)
    today_paid_amount = sum(float(_meta(c).get("amount") or 0) for c in today_paid_rows)

    # 近 N 日 ET
    today_et = to_et(now)
    assert today_et is not None
    day_list = [today_et.date() - timedelta(days=i) for i in range(days - 1, -1, -1)]
    by_day: dict[str, dict] = {
        d.strftime("%Y-%m-%d"): {"date": d.strftime("%Y-%m-%d"), "count": 0, "amount_usd": 0.0}
        for d in day_list
    }
    for c in paid_rows:
        d = _paid_day_et(c)
        if not d:
            continue
        key = d.strftime("%Y-%m-%d")
        if key not in by_day:
            continue
        by_day[key]["count"] += 1
        by_day[key]["amount_usd"] = round(
            by_day[key]["amount_usd"] + float(_meta(c).get("amount") or 0), 2
        )

    return {
        "active_memberships": active_memberships,
        "paid_memberships": paid_memberships,
        "gift_memberships": gift_memberships,
        "trial_memberships": trial_memberships,
        "stripe_subscriptions": stripe_subscriptions,
        "payment_consents": len(all_consents),
        "paid_checkout_count": len(paid_rows),
        "pending_sync_count": len(pending_sync_rows),
        "unpaid_intent_count": unpaid_intent_count,
        "total_paid_amount_usd": round(total_paid_amount, 2),
        "today_paid_count": len(today_paid_rows),
        "today_paid_amount_usd": round(today_paid_amount, 2),
        "payments_by_day": [by_day[d.strftime("%Y-%m-%d")] for d in day_list],
        "days": len(day_list),
        "from_date": day_list[0].strftime("%Y-%m-%d") if day_list else None,
        "to_date": day_list[-1].strftime("%Y-%m-%d") if day_list else None,
        "timezone": str(APP_TZ),
    }


def serialize_consent_payment_row(
    consent: PaymentConsentLog,
    *,
    user_email: str,
    membership: Optional[UserMembership] = None,
    plan_name: Optional[str] = None,
    plan_code: Optional[str] = None,
    user_has_paid_record: bool = False,
    user_has_active_membership: bool = False,
) -> dict[str, Any]:
    extra = _meta(consent)
    display = resolve_display_status(
        consent,
        user_has_paid_record=user_has_paid_record,
        user_has_active_membership=user_has_active_membership,
    )
    kind = resolve_payment_kind(consent)
    return {
        "id": str(consent.id),
        "user_id": str(consent.user_id),
        "user_email": user_email,
        "plan_code": consent.plan_code,
        "billing_cycle": extra.get("billing_interval") or extra.get("billing_cycle") or "",
        "amount": float(extra.get("amount") or 0),
        "currency": str(extra.get("currency") or "usd"),
        "checkout_session_id": _session_id(consent) or None,
        "payment_status": _pay_status(consent),
        "payment_kind": kind,
        "display_status": display,
        "stripe_subscription_id": extra.get("stripe_subscription_id"),
        "paid_at": extra.get("paid_at"),
        "accepted_at": consent.consented_at.isoformat() if consent.consented_at else None,
        "membership": (
            {
                "status": membership.status if membership else None,
                "current_period_end": membership.period_end.isoformat() if membership and membership.period_end else None,
                "plan": {"name": plan_name, "code": plan_code or consent.plan_code},
            }
            if membership or plan_name
            else None
        ),
    }
