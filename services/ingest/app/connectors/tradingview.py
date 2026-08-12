"""TradingView Alert connector — 结构化 JSON 字段映射。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from sigtrades_core.signal.models import Signal, AssetClass
from sigtrades_core.sources.base import BaseSignalSource, NormalizedSignal, Ownership


def _extract_tv_fields(payload: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 TradingView 多种 alert JSON 形态。"""
    # {{strategy.order.action}} 模板嵌套
    strategy = payload.get("strategy") or {}
    order = strategy.get("order") if isinstance(strategy, dict) else {}
    if isinstance(order, dict) and order.get("action"):
        action = str(order["action"]).upper()
    else:
        action = (payload.get("action") or payload.get("side") or payload.get("order_action") or "BUY").upper()

    symbol = (
        payload.get("ticker") or payload.get("symbol") or payload.get("{{ticker}}")
        or (payload.get("instrument") or "")
    )
    if isinstance(symbol, str):
        symbol = symbol.replace("{{ticker}}", "").strip()

    qty = payload.get("quantity") or payload.get("contracts") or payload.get("qty") or 1
    price = payload.get("limit_price") or payload.get("price") or payload.get("close")

    asset = (payload.get("asset_class") or payload.get("asset_type") or "").upper()
    asset_class = AssetClass.STOCK.value if asset in ("STOCK", "STK", "EQUITY") else None

    return {
        "action": action,
        "symbol": str(symbol).upper(),
        "quantity": int(qty) if qty else 1,
        "limit_price": float(price) if price not in (None, "") else None,
        "asset_class": asset_class,
    }


class TradingViewConnector(BaseSignalSource):
    kind = "tradingview"

    @property
    def ownership(self) -> Ownership:
        own = (self.config.get("ownership") or "user_private").lower()
        return Ownership.PLATFORM_SHARED if own == "platform_shared" else Ownership.USER_PRIVATE

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def parse(self, raw: Any) -> List[NormalizedSignal]:
        payload = raw if isinstance(raw, dict) else {"raw_text": str(raw)}
        fields = _extract_tv_fields(payload)
        signal_id = payload.get("signal_id") or payload.get("id") or f"tv-{uuid.uuid4().hex[:12]}"

        sig_kw: Dict[str, Any] = {
            "signal_id": signal_id,
            "timestamp": payload.get("timestamp", time.time()),
            "action": fields["action"],
            "symbol": fields["symbol"],
            "quantity": fields["quantity"],
            "order_type": payload.get("order_type", "MKT"),
            "limit_price": fields["limit_price"],
            "metadata": {"raw": payload, "source": "tradingview"},
        }
        if fields["asset_class"]:
            sig_kw["asset_class"] = fields["asset_class"]

        return [NormalizedSignal(
            signal=Signal(**sig_kw),
            source_id=self.source_id,
            ownership=self.ownership,
            owner_user_id=self.config.get("owner_user_id"),
            raw=payload,
            confidence=1.0 if fields["symbol"] and fields["action"] else 0.5,
        )]
