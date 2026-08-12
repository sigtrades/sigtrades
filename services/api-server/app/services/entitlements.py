"""会员权益门控：has_feature 等。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import MembershipPlan, User, UserMembership


def _membership_effective(m: UserMembership, now: datetime) -> bool:
    if m.status in ("active", "trialing"):
        return m.period_end is None or m.period_end > now
    if m.status in ("past_due", "canceled"):
        return m.period_end is not None and m.period_end > now
    return False


async def get_active_plan(db: AsyncSession, user_id: uuid.UUID) -> Optional[MembershipPlan]:
    """返回当前生效的计划。

    取消/欠费（canceled/past_due）在 period_end 之前仍享受权益（账期宽限），
    到期后由 membership_scheduler 降级为 free。

    优先有到期日的付费/赠送会员，避免注册时留下的 period_end=NULL 的 free 行抢占展示。
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserMembership)
        .options(selectinload(UserMembership.plan))
        .where(
            UserMembership.user_id == user_id,
            UserMembership.status.in_(("active", "trialing", "past_due", "canceled")),
        )
        .order_by(UserMembership.period_end.desc().nullslast(), UserMembership.created_at.desc())
    )
    memberships = [m for m in result.scalars().all() if _membership_effective(m, now)]
    if not memberships:
        return None

    dated_paid = [
        m
        for m in memberships
        if m.period_end is not None and m.plan is not None and m.plan.code != "free"
    ]
    if dated_paid:
        dated_paid.sort(
            key=lambda m: (getattr(m.plan, "sort_order", 0) or 0, m.period_end or now),
            reverse=True,
        )
        return dated_paid[0].plan

    dated_any = [m for m in memberships if m.period_end is not None]
    if dated_any:
        return dated_any[0].plan

    return memberships[0].plan


async def get_active_membership(db: AsyncSession, user_id: uuid.UUID) -> Optional[UserMembership]:
    """返回与 get_active_plan 一致的那条会员记录（用于到期日/账单周期展示）。"""
    now = datetime.now(timezone.utc)
    plan = await get_active_plan(db, user_id)
    if plan is None:
        return None

    result = await db.execute(
        select(UserMembership)
        .options(selectinload(UserMembership.plan))
        .where(
            UserMembership.user_id == user_id,
            UserMembership.plan_id == plan.id,
            UserMembership.status.in_(("active", "trialing", "past_due", "canceled")),
        )
        .order_by(UserMembership.period_end.desc().nullslast(), UserMembership.created_at.desc())
    )
    for m in result.scalars().all():
        if _membership_effective(m, now):
            return m
    return None


def plan_features(plan: Optional[MembershipPlan]) -> Dict[str, Any]:
    if not plan or not plan.features:
        return {
            "auto_trade": False,
            "webhook": False,
            "max_signal_sources": 5,
            "max_brokers": 1,
            "max_discord_channels": 1,
            "discord_multi_channel": False,
            "ai_parse": True,
            "multi_agent": False,
        }
    return dict(plan.features)


async def has_feature(db: AsyncSession, user_id: uuid.UUID, feature: str) -> bool:
    plan = await get_active_plan(db, user_id)
    feats = plan_features(plan)
    val = feats.get(feature)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val > 0
    return bool(val)


async def feature_limit(db: AsyncSession, user_id: uuid.UUID, feature: str, default: int = 0) -> int:
    """读取数值型权益上限（如 max_signal_sources / max_brokers）。"""
    plan = await get_active_plan(db, user_id)
    feats = plan_features(plan)
    val = feats.get(feature, default)
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


async def ensure_within_limit(
    db: AsyncSession, user_id: uuid.UUID, feature: str, current_count: int, default: int = 1
) -> None:
    """计数型额度校验：超限抛 402。"""
    from fastapi import HTTPException

    limit = await feature_limit(db, user_id, feature, default)
    if limit >= 0 and current_count >= limit:
        raise HTTPException(
            status_code=402,
            detail={"error": "plan_limit_exceeded", "feature": feature, "limit": limit},
        )


async def ensure_discord_channels(db: AsyncSession, user_id: uuid.UUID, channel_count: int) -> None:
    """Discord 频道数权益：单频道 vs 多频道。"""
    from fastapi import HTTPException

    if channel_count <= 0:
        return
    max_ch = await feature_limit(db, user_id, "max_discord_channels", default=1)
    if channel_count > max_ch:
        raise HTTPException(
            status_code=402,
            detail={"error": "plan_limit_exceeded", "feature": "max_discord_channels", "limit": max_ch},
        )
    if channel_count > 1 and not await has_feature(db, user_id, "discord_multi_channel"):
        raise HTTPException(
            status_code=402,
            detail={"error": "plan_feature_required", "feature": "discord_multi_channel"},
        )


async def ensure_feature(db: AsyncSession, user_id: uuid.UUID, feature: str) -> None:
    """布尔型权益校验：未开通抛 402。"""
    from fastapi import HTTPException

    if not await has_feature(db, user_id, feature):
        raise HTTPException(
            status_code=402,
            detail={"error": "plan_feature_required", "feature": feature},
        )


async def can_auto_trade(db: AsyncSession, user: User) -> tuple[bool, Optional[str]]:
    if user.kill_switch:
        return False, "kill_switch"
    if not await has_feature(db, user.id, "auto_trade"):
        return False, "plan_no_auto_trade"
    return True, None
