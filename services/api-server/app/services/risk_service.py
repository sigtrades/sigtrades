"""风控校验：交易时段、仓位、止损止盈参数传递。"""

from __future__ import annotations

from datetime import datetime, time as dt_time, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRiskSettings
from app.utils.datetime import et_day_start_utc


def _parse_hm(s: str) -> dt_time:
    h, m = s.split(":")
    return dt_time(int(h), int(m))


def within_trading_hours(hours: Dict[str, Any]) -> bool:
    if not hours:
        return True
    tz = ZoneInfo(hours.get("tz", "America/New_York"))
    now = datetime.now(tz)
    days = hours.get("days", [0, 1, 2, 3, 4])
    if now.weekday() not in days:
        return False
    start = _parse_hm(hours.get("start", "09:30"))
    end = _parse_hm(hours.get("end", "16:00"))
    t = now.time()
    return start <= t <= end


async def load_risk(db: AsyncSession, user_id) -> Optional[UserRiskSettings]:
    result = await db.execute(select(UserRiskSettings).where(UserRiskSettings.user_id == user_id))
    return result.scalar_one_or_none()


async def _daily_loss_usd(db: AsyncSession, user_id) -> float:
    """当日已实现亏损（USD，正数表示亏损额）。

    以券商真实回报为准：聚合今日 execution_reports 中 realized_pnl 为负的成交，
    取其绝对值之和。FAILED/REJECTED 订单未成交，不计入亏损。
    """
    from app.models import ExecutionReportRow

    today = et_day_start_utc()
    result = await db.execute(
        select(ExecutionReportRow).where(
            ExecutionReportRow.user_id == user_id,
            ExecutionReportRow.created_at >= today,
            ExecutionReportRow.status.in_(("FILLED", "PARTIALLY_FILLED")),
        )
    )
    total = 0.0
    for row in result.scalars().all():
        payload = row.payload or {}
        pnl = payload.get("realized_pnl")
        if pnl is None:
            continue
        try:
            pnl_f = float(pnl)
        except (TypeError, ValueError):
            continue
        if pnl_f < 0:
            total += -pnl_f
    return total


async def check_risk(db: AsyncSession, user_id, signal: Dict[str, Any]) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """返回 (allowed, reason, risk_payload 传给 executor)。"""
    risk = await load_risk(db, user_id)
    if not risk or not risk.enabled:
        return True, None, {}

    if risk.trading_hours and not within_trading_hours(risk.trading_hours):
        return False, "outside_trading_hours", {}

    payload: Dict[str, Any] = {}
    if risk.stop_loss_pct is not None:
        payload["stop_loss_pct"] = risk.stop_loss_pct
    if risk.take_profit_pct is not None:
        payload["take_profit_pct"] = risk.take_profit_pct
    if risk.max_position_usd is not None:
        qty = int(signal.get("quantity") or 0)
        price = signal.get("limit_price") or signal.get("metadata", {}).get("ref_price") or 0
        if price and qty * float(price) > risk.max_position_usd:
            return False, "max_position_exceeded", payload

    if risk.max_daily_loss_usd is not None:
        loss = await _daily_loss_usd(db, user_id)
        if loss >= risk.max_daily_loss_usd:
            return False, "max_daily_loss_exceeded", payload

    return True, None, payload
