"""Redis 辅助：幂等缓存（可选，不可用时静默降级）。"""

from __future__ import annotations

import logging
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)

_redis = None
_IDEM_TTL = 86400 * 7  # 7 天


async def get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await _redis.ping()
        return _redis
    except Exception as e:  # noqa: BLE001
        logger.debug("redis unavailable: %s", e)
        _redis = None
        return None


def idem_key(source_id: str, signal_id: str, account_id: Optional[str], user_id: Optional[str] = None) -> str:
    acct = account_id or "_"
    uid = user_id or "_"
    return f"idem:{uid}:{source_id}:{signal_id}:{acct}"


async def idem_cache_get(
    source_id: str, signal_id: str, account_id: Optional[str], user_id: Optional[str] = None
) -> Optional[bool]:
    r = await get_redis()
    if not r:
        return None
    try:
        val = await r.get(idem_key(source_id, signal_id, account_id, user_id))
        if val is None:
            return None
        return val == "1"
    except Exception:  # noqa: BLE001
        return None


_INBOUND_TTL = 86400 * 3  # 3 天：覆盖上游任何重投窗口


def inbound_key(source_id: str, signal_id: str) -> str:
    return f"inbound_seen:{source_id}:{signal_id}"


async def inbound_seen_acquire(source_id: str, signal_id: str) -> Optional[bool]:
    """信号级一次性门闩（SET NX）。

    Returns:
        True: 首次见到该信号；False: 重复投递；None: redis 不可用（调用方应放行）。
    """
    r = await get_redis()
    if not r:
        return None
    try:
        return bool(await r.set(inbound_key(source_id, signal_id), "1", nx=True, ex=_INBOUND_TTL))
    except Exception:  # noqa: BLE001
        return None


async def inbound_seen_release(source_id: str, signal_id: str) -> None:
    """路由中途异常时释放门闩，让上游重投可以恢复。"""
    r = await get_redis()
    if not r:
        return
    try:
        await r.delete(inbound_key(source_id, signal_id))
    except Exception:  # noqa: BLE001
        pass


async def idem_cache_set(
    source_id: str, signal_id: str, account_id: Optional[str], duplicate: bool, user_id: Optional[str] = None
) -> None:
    r = await get_redis()
    if not r:
        return
    try:
        await r.set(
            idem_key(source_id, signal_id, account_id, user_id),
            "1" if duplicate else "0",
            ex=_IDEM_TTL,
        )
    except Exception:  # noqa: BLE001
        pass
