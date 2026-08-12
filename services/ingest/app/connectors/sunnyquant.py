"""SunnyQuant sq_webhook_v2 → SigTrades InboundSignal 归一化。

v2（当前）：与邮件/Bark 同文的 structure_signal，含 title/content/disclaimer +
structure.references，**不含** order / execution / quantity。

执行账号由 URL webhook token 决定；payload.subscriber.user_id 仅作元数据。
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


SUNNYQUANT_CONTRACTS = frozenset({"sq_webhook_v2", "sq_webhook_v1"})


def is_sunnyquant_webhook(payload: Dict[str, Any]) -> bool:
    version = str(payload.get("contract_version") or "").strip()
    if version in SUNNYQUANT_CONTRACTS:
        return True
    return payload.get("source") == "sunnyquant.gex_structure_reminder"


def _execution_to_config(execution: Dict[str, Any]) -> Dict[str, Any]:
    ex = execution or {}
    return {
        "leg_width": ex.get("leg_width") or 20,
        "max_retry_attempts": 5,
        "limit_order_attempts": ex.get("limit_attempts") if ex.get("limit_attempts") is not None else 1,
        "order_wait_timeout": 10,
        "require_confirmation": True,
        "open_order_mode": ex.get("open_order_mode") or "limit_then_market",
        "close_order_mode": ex.get("close_order_mode") or "market",
        "max_trades_per_day": ex.get("max_trades_per_day") or 0,
        "max_same_strike_per_day": ex.get("max_same_strike_per_day") or 0,
        "risk_profile": ex.get("risk_profile") or "balanced",
    }


def _trade_subtype(raw: Any) -> str:
    subtype = str(raw or "ENTRY").upper().replace("-", "_")
    if subtype in {"ENTRY", "OPEN"}:
        return "OPEN"
    if subtype in {"EXIT", "CLOSE", "STOP", "INVALIDATION"} or subtype.startswith("STOP_LOSS"):
        return "CLOSE"
    if subtype in {"TAKE_PROFIT", "REF"}:
        return subtype
    return subtype


def _sunnyquant_metadata(payload: Dict[str, Any], *, content_only: bool, extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    structure = payload.get("structure") if isinstance(payload.get("structure"), dict) else {}
    meta: Dict[str, Any] = {
        "contract_version": payload.get("contract_version"),
        "event": payload.get("event"),
        "audience": payload.get("audience"),
        "strategy_family": payload.get("strategy_family"),
        "signal_subtype": payload.get("signal_subtype"),
        "direction": payload.get("direction"),
        "spx_price": payload.get("spx_price"),
        "title": payload.get("title"),
        "content": payload.get("content"),
        "disclaimer": payload.get("disclaimer"),
        "structure": structure,
        "delivery": payload.get("delivery"),
        "subscriber": payload.get("subscriber"),
        "source": payload.get("source"),
        "content_only": content_only,
    }
    if extra:
        meta.update(extra)
    return {"sunnyquant": meta}


def _is_v2_content_only(payload: Dict[str, Any]) -> bool:
    version = str(payload.get("contract_version") or "").strip()
    if version != "sq_webhook_v2":
        return False
    if payload.get("order"):
        return False
    event = str(payload.get("event") or "").strip()
    if event == "structure_signal":
        return True
    # 无 order 且带 structure / title 的 v2 也按内容契约处理
    return bool(payload.get("structure") or payload.get("title") or payload.get("content"))


def _normalize_v2_content(payload: Dict[str, Any]) -> Dict[str, Any]:
    """sq_webhook_v2 内容型 structure_signal（无 order 块）。"""
    trade_subtype = _trade_subtype(payload.get("signal_subtype"))
    return {
        "signal_id": str(payload.get("signal_id") or ""),
        "timestamp": payload.get("timestamp") or time.time(),
        "type": "STRUCTURE_SIGNAL",
        "action": "",
        "symbol": "SPX",
        "quantity": 0,
        "order_type": "MKT",
        "limit_price": None,
        "time_in_force": "DAY",
        "strategy": payload.get("strategy") or "GEX",
        "legs": None,
        "signal_category": "ALERT",
        "signal_subtype": trade_subtype,
        "asset_class": payload.get("asset_class") or "SPX_OPTIONS",
        "auto_trade_enabled": False,
        "metadata": _sunnyquant_metadata(payload, content_only=True),
        "execution_config": None,
    }


def _normalize_v1_to_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy sq_webhook_v1：metadata 壳，无 order。"""
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    strategy = payload.get("strategy") or payload.get("strategy_code") or "GEX"
    return {
        "signal_id": str(payload.get("signal_id") or ""),
        "timestamp": payload.get("timestamp") or time.time(),
        "type": "ORDER",
        "action": "",
        "symbol": "SPX",
        "quantity": 0,
        "order_type": "MKT",
        "limit_price": None,
        "time_in_force": "DAY",
        "strategy": strategy,
        "legs": None,
        "signal_category": "ALERT",
        "signal_subtype": _trade_subtype(payload.get("signal_subtype_trade") or payload.get("signal_subtype")),
        "asset_class": payload.get("asset_class") or "SPX_OPTIONS",
        "auto_trade_enabled": False,
        "metadata": {
            "sunnyquant": {
                "contract_version": payload.get("contract_version"),
                "audience": payload.get("audience"),
                "structure": meta,
                "legacy_v1": True,
            }
        },
        "execution_config": _execution_to_config(payload.get("execution_preferences") or {}),
    }


_LEG_KEYS = ("symbol", "action", "quantity", "limit_price", "strike", "option_type")


def _normalize_legs(raw_legs: Any) -> Optional[list]:
    """只保留 OptionLeg 已知字段，quantity 缺省补 1（防未知键使 OptionLeg(**leg) 崩溃）。"""
    if not isinstance(raw_legs, list):
        return None
    legs = []
    for item in raw_legs:
        if not isinstance(item, dict):
            continue
        leg = {k: item[k] for k in _LEG_KEYS if k in item}
        if not leg.get("symbol"):
            continue
        leg.setdefault("action", "SELL")
        leg["quantity"] = int(leg.get("quantity") or 1)
        legs.append(leg)
    return legs or None


def _normalize_v2_order(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Legacy sq_webhook_v2 + order 块（内部测试 / 旧契约）。"""
    order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
    execution = payload.get("execution") if isinstance(payload.get("execution"), dict) else {}
    trade_subtype = _trade_subtype(payload.get("signal_subtype_trade") or payload.get("signal_subtype"))

    return {
        "signal_id": str(payload.get("signal_id") or ""),
        "timestamp": payload.get("timestamp") or time.time(),
        "type": order.get("type") or "ORDER",
        "action": order.get("action") or "",
        "symbol": order.get("symbol") or "SPX",
        "quantity": int(order.get("quantity") or 1),
        "order_type": order.get("order_type") or "LMT",
        "limit_price": order.get("limit_price"),
        "time_in_force": order.get("time_in_force") or "DAY",
        "strategy": payload.get("strategy") or "GEX",
        "legs": _normalize_legs(order.get("legs")),
        "signal_category": "TRADE",
        "signal_subtype": trade_subtype,
        "asset_class": payload.get("asset_class") or "SPX_OPTIONS",
        "auto_trade_enabled": True,
        "metadata": _sunnyquant_metadata(
            payload,
            content_only=False,
            extra={
                "execution": execution,
                "combo": order.get("combo"),
            },
        ),
        "execution_config": _execution_to_config(execution),
    }


def sunnyquant_payload_to_signal(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = str(payload.get("contract_version") or "").strip()
    if version == "sq_webhook_v1" or (version != "sq_webhook_v2" and not payload.get("order") and payload.get("metadata")):
        return _normalize_v1_to_signal(payload)
    if _is_v2_content_only(payload):
        return _normalize_v2_content(payload)
    if payload.get("order"):
        return _normalize_v2_order(payload)
    return _normalize_v2_content(payload)


def parse_sunnyquant_webhook(
    payload: Dict[str, Any],
    source_id: str,
    owner_user_id: Optional[str],
) -> Optional[Tuple[str, Dict[str, Any]]]:
    if not is_sunnyquant_webhook(payload):
        return None
    signal = sunnyquant_payload_to_signal(payload)
    signal_id = str(signal.get("signal_id") or "").strip()
    if not signal_id:
        return None
    if not signal.get("action") and signal.get("legs"):
        signal["action"] = "组合"
    return signal_id, {
        "source_id": source_id,
        "signal_id": signal_id,
        "signal": signal,
        "ownership": "user_private",
        "owner_user_id": owner_user_id,
    }
