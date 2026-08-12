"""会员降级时同步收紧执行动作（自动下单 → 确认后下单）。"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRouteRule

logger = logging.getLogger(__name__)


async def demote_auto_trade_rules(db: AsyncSession, user_id: uuid.UUID) -> int:
    """将用户所有 auto_trade / both 路由改为 confirm_trade。"""
    result = await db.execute(
        select(UserRouteRule).where(
            UserRouteRule.user_id == user_id,
            UserRouteRule.action.in_(("auto_trade", "both")),
        )
    )
    n = 0
    for rule in result.scalars().all():
        rule.action = "confirm_trade"
        n += 1
    if n:
        logger.info("Demoted %d auto-trade route rule(s) for user %s → confirm_trade", n, user_id)
    return n
