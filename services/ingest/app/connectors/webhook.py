"""Webhook 连接器：TradingView / SunnyQuant / 通用 JSON → InboundSignal。"""

from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Any, Dict, Optional, Tuple

from app.connectors.sunnyquant import parse_sunnyquant_webhook


def verify_hmac(
    body: bytes,
    signature: Optional[str],
    secret: Optional[str],
    *,
    require_secret: bool = False,
) -> bool:
    if not secret:
        if require_secret:
            return False
        return True  # dev：未配置 HMAC 则跳过
    if not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def parse_webhook_payload(
    payload: Dict[str, Any],
    source_id: str,
    owner_user_id: Optional[str],
) -> Tuple[str, Dict[str, Any]]:
    """把 webhook JSON 归一化为 signal-router InboundSignal 信封。"""
    sq = parse_sunnyquant_webhook(payload, source_id, owner_user_id)
    if sq is not None:
        return sq

    contract = str(payload.get("contract_version") or "").strip()
    is_st_v1 = contract == "st_webhook_v1"
    # SigTrades 标准 JSON / 已结构化信号（signal_id + action）
    if is_st_v1 or (payload.get("signal_id") and payload.get("action")):
        signal = dict(payload)
        signal_id = str(signal.pop("signal_id", None) or f"st-{uuid.uuid4().hex[:12]}")
        signal.pop("contract_version", None)
        signal.setdefault("timestamp", time.time())
        if is_st_v1:
            meta = dict(signal.get("metadata") or {})
            meta.setdefault("contract_version", "st_webhook_v1")
            signal["metadata"] = meta
        if not signal.get("action") and is_st_v1:
            signal["action"] = "BUY"
        return signal_id, {
            "source_id": source_id,
            "signal_id": signal_id,
            "signal": signal,
            "ownership": "user_private",
            "owner_user_id": owner_user_id,
        }

    # TradingView alert 常见格式
    if "ticker" in payload or "symbol" in payload:
        symbol = payload.get("ticker") or payload.get("symbol", "")
        action = (payload.get("action") or payload.get("side") or "BUY").upper()
        signal_id = payload.get("id") or f"wh-{uuid.uuid4().hex[:12]}"
        signal = {
            "signal_id": signal_id,
            "timestamp": time.time(),
            "action": action,
            "symbol": symbol,
            "quantity": int(payload.get("quantity") or payload.get("contracts") or 1),
            "order_type": payload.get("order_type", "MKT"),
            "limit_price": payload.get("limit_price") or payload.get("price"),
            "metadata": {"raw": payload},
        }
        sym = str(symbol).upper()
        if sym and " " not in sym and len(sym) <= 6:
            signal["asset_class"] = "STOCK"
        return signal_id, {
            "source_id": source_id,
            "signal_id": signal_id,
            "signal": signal,
            "ownership": "user_private",
            "owner_user_id": owner_user_id,
        }

    # 纯文本/未知：透传 raw，由 api-server 解析规则处理
    signal_id = f"wh-{uuid.uuid4().hex[:12]}"
    signal = {
        "signal_id": signal_id,
        "timestamp": time.time(),
        "type": "ORDER",
        "action": "",
        "symbol": "",
        "quantity": 0,
        "order_type": "MKT",
        "metadata": {"raw_text": str(payload), "parse_pending": True},
    }
    return signal_id, {
        "source_id": source_id,
        "signal_id": signal_id,
        "signal": signal,
        "ownership": "user_private",
        "owner_user_id": owner_user_id,
    }
