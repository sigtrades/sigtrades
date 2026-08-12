"""全站业务时间统一为美东 (America/New_York)。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

APP_TZ = ZoneInfo("America/New_York")
ET_LABEL = "ET"


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_et(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return ensure_utc(dt).astimezone(APP_TZ)


def format_et(dt: Optional[datetime]) -> Optional[str]:
    """用户可见时间：YYYY-MM-DD HH:MM:SS ET"""
    if dt is None:
        return None
    et = to_et(dt)
    assert et is not None
    return et.strftime(f"%Y-%m-%d %H:%M:%S {ET_LABEL}")


def et_day_start_utc(now: Optional[datetime] = None) -> datetime:
    """当前美东日历日 00:00:00 对应的 UTC 时刻（用于「今日」统计）。"""
    ref = to_et(now or datetime.now(timezone.utc))
    assert ref is not None
    start_et = ref.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_et.astimezone(timezone.utc)
