"""从 signal JSON / 成交回报提取可落库的执行属性。"""

from __future__ import annotations

from typing import Any, Optional


def extract_channel_id(signal: dict[str, Any] | None) -> Optional[str]:
    """Discord channel_id 或 Telegram chat_id，统一写入 execution_records.channel_id。"""
    if not signal or not isinstance(signal, dict):
        return None
    meta = signal.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    for key in ("channel_id", "chat_id"):
        raw = meta.get(key)
        if raw is None or raw == "":
            continue
        return str(raw).strip()[:64] or None
    return None


def extract_signal_subtype(signal: dict[str, Any] | None) -> Optional[str]:
    if not signal or not isinstance(signal, dict):
        return None
    raw = signal.get("signal_subtype") or signal.get("signal_subtype_trade")
    if raw is None or raw == "":
        return None
    value = str(raw).strip().upper()
    if value in {"ENTRY", "OPEN"}:
        return "OPEN"
    if value in {"EXIT", "CLOSE", "STOP", "INVALIDATION"} or value.startswith("STOP_LOSS"):
        return "CLOSE"
    return value[:32]


def coerce_realized_pnl(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
