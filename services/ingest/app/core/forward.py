"""转发归一化信号到 signal-router（含 AI/规则解析）。"""

from __future__ import annotations

import logging
from typing import Any, Dict

import httpx

from app.config import settings
from app.core.parse_client import enrich_inbound

logger = logging.getLogger(__name__)


async def _notify_parse_failed(payload: Dict[str, Any]) -> None:
    owner = payload.get("owner_user_id")
    if not owner:
        return
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(
                f"{settings.API_SERVER_URL}/internal/notify",
                json={
                    "user_id": owner,
                    "kind": "parse_failed",
                    "language": "zh",
                    "source_id": payload.get("source_id", ""),
                    "signal_id": payload.get("signal_id", ""),
                    "extra": {"signal": payload.get("signal")},
                },
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("parse_failed notify error: %s", e)


async def forward_inbound(payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = await enrich_inbound(payload)
    sig = payload.get("signal") or {}
    if not sig.get("action") or not sig.get("symbol"):
        await _notify_parse_failed(payload)
        return {"skipped": True, "reason": "parse_failed", "signal_id": payload.get("signal_id")}

    # 路由侧云执行已异步下发；此处只需等 resolve+dispatch，不必等成交
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=20.0) as client:
            resp = await client.post(
                f"{settings.SIGNAL_ROUTER_URL}/signal",
                json=payload,
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException as e:
        logger.error("forward to signal-router timeout: %s", e)
        return {
            "routed": 0,
            "deferred": True,
            "reason": "router_timeout",
            "signal_id": payload.get("signal_id"),
            "detail": str(e),
        }
    except httpx.HTTPError as e:
        logger.error("forward to signal-router failed: %s", e)
        return {
            "routed": 0,
            "error": True,
            "reason": "router_unreachable",
            "signal_id": payload.get("signal_id"),
            "detail": str(e),
        }


async def forward_to_router(payload: Dict[str, Any]) -> Dict[str, Any]:
    return await forward_inbound(payload)
