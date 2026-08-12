"""调用 api-server 解析信号并合并到 inbound 信封。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _needs_parse(signal: Dict[str, Any]) -> bool:
    meta = signal.get("metadata") or {}
    if meta.get("parse_pending"):
        return True
    if not signal.get("action") or not signal.get("symbol"):
        return True
    return False


async def enrich_inbound(inbound: Dict[str, Any]) -> Dict[str, Any]:
    """若信号未结构化，调用 /internal/parse-signal 补全。"""
    signal = dict(inbound.get("signal") or {})
    if not _needs_parse(signal):
        return inbound

    owner = inbound.get("owner_user_id")
    source_id = inbound.get("source_id")
    if not owner or not source_id:
        return inbound

    meta = signal.get("metadata") or {}
    sample = meta.get("raw_text")
    if not sample and meta.get("raw"):
        sample = str(meta["raw"])
    if not sample:
        sample = signal
    author = meta.get("author")
    if author and isinstance(sample, str):
        sample = {"raw_text": sample, "author": str(author)}

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=20.0) as client:
            resp = await client.post(
                f"{settings.API_SERVER_URL}/internal/parse-signal",
                json={"user_id": owner, "source_id": source_id, "sample": sample},
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        resp.raise_for_status()
        data = resp.json()
        parsed = data.get("signal") or {}
        # 解析结果会生成 parse-xxx 临时 id，必须保留原始 dc-/tg- 信号 id，否则执行回报无法回写同一条流水线记录。
        preserve_keys = {"signal_id", "timestamp"}
        original_signal_id = signal.get("signal_id") or inbound.get("signal_id")
        merged = {
            **signal,
            **{
                k: v
                for k, v in parsed.items()
                if v not in (None, "", 0) and k not in preserve_keys
            },
        }
        if original_signal_id:
            merged["signal_id"] = original_signal_id
        if data.get("confidence"):
            merged.setdefault("metadata", {})["parse_confidence"] = data["confidence"]
            merged["metadata"]["parse_mode"] = data.get("mode")
        inbound = {**inbound, "signal": merged, "signal_id": merged.get("signal_id") or inbound.get("signal_id")}
    except Exception as e:  # noqa: BLE001
        logger.warning("parse-signal failed source=%s: %s", source_id, e)
    return inbound
