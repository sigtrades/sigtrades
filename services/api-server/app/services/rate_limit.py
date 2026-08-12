"""轻量限流：优先用 Redis（多实例共享），不可用时回退进程内计数。

用作 FastAPI 依赖：`Depends(rate_limit("login", limit=10, window=60))`。
按 客户端IP + scope 维度计数，超限返回 429。
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict

from fastapi import HTTPException, Request

from app.services.redis_client import get_redis

# 进程内回退：scope:ip -> 时间戳队列
_local: Dict[str, Deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _allow_redis(key: str, limit: int, window: int) -> bool | None:
    r = await get_redis()
    if not r:
        return None
    try:
        cnt = await r.incr(key)
        if cnt == 1:
            await r.expire(key, window)
        return cnt <= limit
    except Exception:  # noqa: BLE001
        return None


def _allow_local(key: str, limit: int, window: int) -> bool:
    now = time.time()
    q = _local[key]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        return False
    q.append(now)
    return True


def rate_limit(scope: str, limit: int = 10, window: int = 60) -> Callable:
    async def _dep(request: Request) -> None:
        ip = _client_ip(request)
        key = f"rl:{scope}:{ip}"
        allowed = await _allow_redis(key, limit, window)
        if allowed is None:
            allowed = _allow_local(key, limit, window)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={"error": "rate_limited", "scope": scope, "retry_after": window},
                headers={"Retry-After": str(window)},
            )

    return _dep
