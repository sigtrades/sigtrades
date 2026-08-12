"""会员到期降级调度。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select

from app.database import SessionLocal
from app.models import MembershipPlan, UserMembership
from app.services.plan_downgrade import demote_auto_trade_rules

logger = logging.getLogger(__name__)


async def cleanup_shadow_free_memberships() -> int:
    """作废：用户已有未过期付费/赠送会员时，仍 active 且无到期日的 free 行。"""
    now = datetime.now(timezone.utc)
    count = 0
    async with SessionLocal() as db:
        free = await db.execute(select(MembershipPlan).where(MembershipPlan.code == "free"))
        free_plan = free.scalar_one_or_none()
        if not free_plan:
            return 0
        paid = await db.execute(
            select(UserMembership).where(
                UserMembership.status.in_(("active", "trialing")),
                UserMembership.period_end.isnot(None),
                UserMembership.period_end > now,
                UserMembership.plan_id != free_plan.id,
            )
        )
        user_ids = {m.user_id for m in paid.scalars().all()}
        if not user_ids:
            return 0
        shadows = await db.execute(
            select(UserMembership).where(
                UserMembership.user_id.in_(user_ids),
                UserMembership.plan_id == free_plan.id,
                UserMembership.status.in_(("active", "trialing")),
                UserMembership.period_end.is_(None),
            )
        )
        for m in shadows.scalars().all():
            m.status = "expired"
            count += 1
        if count:
            await db.commit()
            logger.info("Expired %d shadow free membership row(s)", count)
    return count


async def downgrade_expired_once() -> int:
    now = datetime.now(timezone.utc)
    count = 0
    async with SessionLocal() as db:
        free = await db.execute(select(MembershipPlan).where(MembershipPlan.code == "free"))
        free_plan = free.scalar_one_or_none()
        if not free_plan:
            return 0

        result = await db.execute(
            select(UserMembership).where(
                UserMembership.period_end.isnot(None),
                UserMembership.period_end < now,
                UserMembership.status.in_(("active", "trialing", "past_due", "canceled")),
            )
        )
        demote_user_ids: list = []
        for m in result.scalars().all():
            demote_user_ids.append(m.user_id)
            m.status = "expired"
            m.plan_id = free_plan.id
            m.stripe_subscription_id = None
            count += 1
        for uid in {u for u in demote_user_ids}:
            await demote_auto_trade_rules(db, uid)
        if count:
            await db.commit()
            logger.info("降级过期会员 %d 条", count)
    return count


async def membership_scheduler_loop(interval_sec: int = 3600) -> None:
    while True:
        try:
            await cleanup_shadow_free_memberships()
            await downgrade_expired_once()
        except Exception as e:  # noqa: BLE001
            logger.error("membership scheduler error: %s", e)
        await asyncio.sleep(interval_sec)
