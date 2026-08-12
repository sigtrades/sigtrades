"""Alpaca Trading API adapter for paper and live cloud execution."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.brokers.status_mapping import AlpacaStatusMapper
from sigtrades_core.signal.models import OptionLeg, Signal
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_alpaca_option_symbol,
    parse_option_symbol,
)
from sigtrades_core.trading.order_status import OrderStatus

logger = logging.getLogger(__name__)

_PAPER_BASE_URL = "https://paper-api.alpaca.markets"
_LIVE_BASE_URL = "https://api.alpaca.markets"


class AlpacaBrokerAdapter(BaseBrokerAdapter):
    """Alpaca Trading API adapter using account API keys."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = (config.get("api_key") or config.get("key_id") or "").strip()
        self.api_secret = (config.get("api_secret") or config.get("secret_key") or "").strip()
        self.env = (config.get("env") or "paper").strip().lower()
        default_url = _LIVE_BASE_URL if self.env == "live" else _PAPER_BASE_URL
        self.base_url = (config.get("base_url") or default_url).rstrip("/")
        self._client = httpx.Client(timeout=20.0)

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.api_secret,
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self._headers())
        response = self._client.request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            **kwargs,
        )
        response.raise_for_status()
        return response

    def connect(self) -> bool:
        self.connect_error = None
        self.connected = False
        if not self.api_key or not self.api_secret:
            self.connect_error = "Alpaca 凭证不完整：需提供 API Key 与 API Secret"
            return False
        try:
            self._request("GET", "/v2/account")
            self.connected = True
            return True
        except Exception as exc:
            self.connect_error = self._error_detail(exc)
            logger.exception("Alpaca 连接失败: %s", self.connect_error)
            return False

    def disconnect(self) -> bool:
        self._client.close()
        self.connected = False
        return True

    def get_account_info(self) -> Dict[str, Any]:
        return self._request("GET", "/v2/account").json()

    def get_option_positions(self) -> List[Dict[str, Any]]:
        positions = self._request("GET", "/v2/positions").json()
        return [
            row
            for row in positions
            if str(row.get("asset_class") or "").lower() in ("us_option", "option")
        ]

    def supports_combined_order(self) -> bool:
        # Level 3 / mleg：见 https://docs.alpaca.markets/us/docs/options-level-3-trading
        return True

    @staticmethod
    def _is_option(signal: Signal) -> bool:
        asset_class = (signal.asset_class or "").upper()
        metadata = signal.metadata or {}
        return (
            asset_class in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS")
            or bool(metadata.get("strike"))
            or bool(signal.legs)
        )

    def _resolve_option_symbol(
        self,
        symbol: str,
        *,
        metadata: Optional[Dict[str, Any]] = None,
        strike: Optional[float] = None,
        right: Optional[str] = None,
    ) -> str:
        parsed = parse_option_symbol(
            symbol,
            metadata=metadata or {},
            underlying=(metadata or {}).get("underlying"),
            strike=strike if strike is not None else (metadata or {}).get("strike"),
            right=right
            or (metadata or {}).get("right")
            or (metadata or {}).get("option_type"),
            expiry=(metadata or {}).get("expiry") or (metadata or {}).get("expiry_date"),
        )
        return format_alpaca_option_symbol(
            ParsedOption(
                underlying=parsed["underlying"],
                strike=float(parsed["strike"]),
                right=parsed["right"],
                put_call=parsed["put_call"],
                expiry=parsed["expiry"],
                expiry_contract=parsed["expiry_contract"],
            )
        )

    def _resolve_symbol(self, signal: Signal) -> tuple[str, bool]:
        metadata = signal.metadata or {}
        if not self._is_option(signal):
            symbol = (signal.symbol or metadata.get("underlying") or "").strip().upper()
            if not symbol:
                raise ValueError("Alpaca 股票订单缺少 symbol")
            return symbol, False
        return self._resolve_option_symbol(signal.symbol, metadata=metadata), True

    @staticmethod
    def _is_close(signal: Signal) -> bool:
        subtype = (signal.signal_subtype or "").strip().upper()
        return subtype in ("CLOSE", "EXIT", "COVER")

    @classmethod
    def _position_intent_for_action(cls, action: str, *, is_close: bool) -> str:
        key = (action or "BUY").strip().upper()
        allowed = {"BUY_TO_OPEN", "BUY_TO_CLOSE", "SELL_TO_OPEN", "SELL_TO_CLOSE"}
        if key in allowed:
            return key.lower()
        side_sell = key.startswith("SELL")
        if side_sell:
            return "sell_to_close" if is_close else "sell_to_open"
        return "buy_to_close" if is_close else "buy_to_open"

    @classmethod
    def _position_intent(cls, signal: Signal) -> str:
        return cls._position_intent_for_action(signal.action or "BUY", is_close=cls._is_close(signal))

    @staticmethod
    def _decimal_text(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f")

    @staticmethod
    def _tif(signal: Signal) -> str:
        return (
            "gtc"
            if (signal.time_in_force or "DAY").upper() in ("GTC", "GOOD_TIL_CANCELED")
            else "day"
        )

    def _mleg_leg_payload(self, leg: OptionLeg, signal: Signal) -> Dict[str, Any]:
        symbol = self._resolve_option_symbol(
            leg.symbol,
            metadata=signal.metadata,
            strike=leg.strike,
            right=leg.option_type,
        )
        action = (leg.action or "BUY").strip().upper()
        side = "sell" if action.startswith("SELL") else "buy"
        return {
            "symbol": symbol,
            "ratio_qty": str(max(1, int(leg.quantity or 1))),
            "side": side,
            "position_intent": self._position_intent_for_action(
                action, is_close=self._is_close(signal)
            ),
        }

    def _mleg_order_payload(self, signal: Signal) -> Dict[str, Any]:
        """Alpaca Level 3 multi-leg：order_class=mleg。"""
        legs = list(signal.legs or [])
        if len(legs) < 2 or len(legs) > 4:
            raise ValueError("Alpaca 多腿订单需 2–4 条期权腿")
        order_type = (signal.order_type or "LMT").upper()
        if order_type not in ("LMT", "LIMIT", "MKT", "MARKET"):
            raise ValueError(f"Alpaca 暂不支持订单类型: {order_type}")
        is_market = order_type in ("MKT", "MARKET")
        payload: Dict[str, Any] = {
            "order_class": "mleg",
            "qty": str(max(1, int(signal.quantity or 1))),
            "type": "market" if is_market else "limit",
            "time_in_force": self._tif(signal),
            "legs": [self._mleg_leg_payload(leg, signal) for leg in legs],
        }
        if not is_market:
            price = signal.limit_price
            if price is None:
                for leg in legs:
                    if leg.limit_price is not None:
                        price = leg.limit_price
                        break
            if price is None:
                raise ValueError("Alpaca 多腿限价单缺少 limit_price（净权利金）")
            payload["limit_price"] = self._decimal_text(abs(float(price)))
        return payload

    def _order_payload(self, signal: Signal) -> Dict[str, Any]:
        if signal.legs and len(signal.legs) > 1:
            return self._mleg_order_payload(signal)
        symbol, is_option = self._resolve_symbol(signal)
        order_type = (signal.order_type or "LMT").upper()
        if order_type not in ("LMT", "LIMIT", "MKT", "MARKET"):
            raise ValueError(f"Alpaca 暂不支持订单类型: {order_type}")
        is_market = order_type in ("MKT", "MARKET")
        raw_action = (signal.action or "BUY").strip().upper()
        side = "sell" if raw_action.startswith("SELL") else "buy"
        payload: Dict[str, Any] = {
            "symbol": symbol,
            "qty": str(max(1, int(signal.quantity or 1))),
            "side": side,
            "type": "market" if is_market else "limit",
            "time_in_force": self._tif(signal),
        }
        if is_option:
            payload["position_intent"] = self._position_intent(signal)
        if not is_market:
            price = signal.limit_price
            if price is None and signal.legs:
                price = signal.legs[0].limit_price
            if price is None:
                raise ValueError("Alpaca 限价单缺少 limit_price")
            payload["limit_price"] = self._decimal_text(float(price))
        return payload

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        if not self.connected and not self.connect():
            return {
                "order_id": None,
                "status": "FAILED",
                "error": self.connect_error or "Alpaca 未连接",
            }
        try:
            response = self._request(
                "POST",
                "/v2/orders",
                json=self._order_payload(signal),
                headers={"Content-Type": "application/json"},
            )
            order_id = str(response.json().get("id") or "")
            if not order_id:
                raise RuntimeError("Alpaca 下单响应未包含订单 ID")
            return {"order_id": order_id, "status": "SUCCESS", "error": None}
        except Exception as exc:
            error = self._error_detail(exc)
            logger.exception("Alpaca 下单失败: %s", error)
            return {"order_id": None, "status": "FAILED", "error": error}

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._request("DELETE", f"/v2/orders/{order_id}")
            return True
        except Exception as exc:
            logger.error("Alpaca 撤单失败 order_id=%s: %s", order_id, self._error_detail(exc))
            return False

    @staticmethod
    def _normalize_order(row: Dict[str, Any]) -> Dict[str, Any]:
        raw_status = str(row.get("status") or "")
        standard = AlpacaStatusMapper.to_standard(raw_status)
        quantity = float(row.get("qty") or 0)
        filled_quantity = float(row.get("filled_qty") or 0)
        if (
            standard == OrderStatus.SUBMITTED
            and filled_quantity > 0
            and filled_quantity < quantity
        ):
            standard = OrderStatus.PARTIALLY_FILLED
        fill_price_raw = row.get("filled_avg_price")
        return {
            "order_id": str(row.get("id") or ""),
            "symbol": row.get("symbol") or "",
            "status": standard.value,
            "order_status": standard.value,
            "broker_status": raw_status,
            "quantity": int(quantity),
            "filled_quantity": filled_quantity,
            "filled_qty": filled_quantity,
            "fill_price": float(fill_price_raw) if fill_price_raw is not None else None,
            "filled_price": float(fill_price_raw) if fill_price_raw is not None else None,
            "limit_price": float(row.get("limit_price") or 0),
            "action": str(row.get("side") or "").upper(),
        }

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        try:
            return self._normalize_order(
                self._request("GET", f"/v2/orders/{order_id}").json()
            )
        except Exception as exc:
            logger.warning("Alpaca 查询订单失败 order_id=%s: %s", order_id, self._error_detail(exc))
            return None

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            rows = self._request(
                "GET",
                "/v2/orders",
                params={"status": "all", "limit": 100, "nested": "false"},
            ).json()
            orders = [self._normalize_order(row) for row in rows]
            if status:
                target = status.upper()
                orders = [row for row in orders if row["status"].upper() == target]
            return orders
        except Exception as exc:
            logger.error("Alpaca 查询订单列表失败: %s", self._error_detail(exc))
            return []

    @staticmethod
    def _error_detail(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            try:
                body = response.json()
            except Exception:
                body = response.text
            return f"HTTP {response.status_code}: {body}"
        return str(exc)
