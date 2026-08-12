"""Charles Schwab Trader API adapter (cloud OAuth execution).

Supports US equities and single-leg options. Multi-leg strategies and
protective child orders are intentionally not advertised until their lifecycle
is covered by the shared execution state machine.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.brokers.status_mapping import SchwabStatusMapper
from sigtrades_core.signal.models import Signal
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_schwab_option_symbol,
    parse_option_symbol,
)
from sigtrades_core.trading.order_status import OrderStatus

logger = logging.getLogger(__name__)

_TRADER_BASE_URL = "https://api.schwabapi.com/trader/v1"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


class SchwabBrokerAdapter(BaseBrokerAdapter):
    """Schwab Trader API adapter using a user-authorized refresh token."""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.client_id = (config.get("client_id") or config.get("app_key") or "").strip()
        self.client_secret = (config.get("client_secret") or config.get("app_secret") or "").strip()
        self.refresh_token = (config.get("refresh_token") or "").strip()
        self.account_hash = (config.get("account_hash") or "").strip()
        self.account_number = (config.get("account_number") or config.get("account_id") or "").strip()
        self.base_url = (config.get("base_url") or _TRADER_BASE_URL).rstrip("/")
        self.token_url = config.get("token_url") or _TOKEN_URL
        self.access_token = (config.get("access_token") or "").strip()
        self._client = httpx.Client(timeout=20.0)

    def _credentials_complete(self) -> bool:
        return bool(
            self.client_id
            and self.client_secret
            and self.refresh_token
            and self.account_hash
        )

    def _refresh_access_token(self) -> None:
        response = self._client.post(
            self.token_url,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise RuntimeError("Schwab OAuth refresh response missing access_token")
        self.access_token = token
        # Schwab may return a renewed refresh token. Keep it in memory for this
        # execution process; the UI still surfaces the documented re-auth need.
        renewed_refresh = str(payload.get("refresh_token") or "").strip()
        if renewed_refresh:
            self.refresh_token = renewed_refresh

    def _headers(self) -> Dict[str, str]:
        if not self.access_token:
            self._refresh_access_token()
        return {
            "Authorization": f"Bearer {self.access_token}",
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
        if response.status_code == 401:
            self._refresh_access_token()
            headers["Authorization"] = f"Bearer {self.access_token}"
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
        if not self._credentials_complete():
            self.connect_error = (
                "Schwab 凭证不完整：请先完成 OAuth 授权（需 Client ID、Client Secret、Refresh Token、hashValue）"
            )
            return False
        try:
            self._refresh_access_token()
            self._request("GET", f"/accounts/{self.account_hash}")
            self.connected = True
            return True
        except Exception as exc:
            self.connect_error = self._error_detail(exc)
            logger.exception("Schwab 连接失败: %s", self.connect_error)
            return False

    def disconnect(self) -> bool:
        self._client.close()
        self.connected = False
        self.access_token = ""
        return True

    def get_account_info(self) -> Dict[str, Any]:
        response = self._request(
            "GET",
            f"/accounts/{self.account_hash}",
            params={"fields": "positions"},
        )
        return response.json()

    def get_option_positions(self) -> List[Dict[str, Any]]:
        account = self.get_account_info()
        securities = account.get("securitiesAccount") or {}
        positions = securities.get("positions") or []
        return [
            position
            for position in positions
            if str((position.get("instrument") or {}).get("assetType") or "").upper()
            == "OPTION"
        ]

    def supports_combined_order(self) -> bool:
        return False

    @staticmethod
    def _is_option(signal: Signal) -> bool:
        asset_class = (signal.asset_class or "").upper()
        metadata = signal.metadata or {}
        return (
            asset_class in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS")
            or bool(metadata.get("strike"))
        )

    def _resolve_symbol(self, signal: Signal) -> tuple[str, str]:
        metadata = signal.metadata or {}
        if not self._is_option(signal):
            symbol = (signal.symbol or metadata.get("underlying") or "").strip().upper()
            if not symbol:
                raise ValueError("Schwab 股票订单缺少 symbol")
            return symbol, "EQUITY"

        parsed = parse_option_symbol(
            signal.symbol,
            metadata=metadata,
            underlying=metadata.get("underlying"),
            strike=metadata.get("strike"),
            right=metadata.get("right") or metadata.get("option_type"),
            expiry=metadata.get("expiry") or metadata.get("expiry_date"),
        )
        symbol = format_schwab_option_symbol(
            ParsedOption(
                underlying=parsed["underlying"],
                strike=float(parsed["strike"]),
                right=parsed["right"],
                put_call=parsed["put_call"],
                expiry=parsed["expiry"],
                expiry_contract=parsed["expiry_contract"],
            )
        )
        return symbol, "OPTION"

    @staticmethod
    def _instruction(signal: Signal, asset_type: str) -> str:
        action = (signal.action or "BUY").strip().upper()
        if asset_type == "EQUITY":
            allowed = {"BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER"}
            return action if action in allowed else "BUY"

        allowed = {"BUY_TO_OPEN", "BUY_TO_CLOSE", "SELL_TO_OPEN", "SELL_TO_CLOSE"}
        if action in allowed:
            return action
        is_close = (signal.signal_subtype or "").upper() == "CLOSE"
        if action == "SELL":
            return "SELL_TO_CLOSE" if is_close or not signal.signal_subtype else "SELL_TO_OPEN"
        return "BUY_TO_CLOSE" if is_close else "BUY_TO_OPEN"

    @staticmethod
    def _decimal_text(value: float) -> str:
        return format(Decimal(str(value)).normalize(), "f")

    def _order_payload(self, signal: Signal) -> Dict[str, Any]:
        if signal.legs and len(signal.legs) > 1:
            raise ValueError("Schwab 当前仅支持股票和单腿期权订单")
        symbol, asset_type = self._resolve_symbol(signal)
        order_type = (signal.order_type or "LMT").upper()
        if order_type not in ("LMT", "LIMIT", "MKT", "MARKET"):
            raise ValueError(f"Schwab 暂不支持订单类型: {order_type}")
        is_market = order_type in ("MKT", "MARKET")
        quantity = max(1, int(signal.quantity or 1))
        payload: Dict[str, Any] = {
            "session": "NORMAL",
            "duration": (
                "GOOD_TILL_CANCEL"
                if (signal.time_in_force or "DAY").upper() in ("GTC", "GOOD_TIL_CANCELED")
                else "DAY"
            ),
            "orderType": "MARKET" if is_market else "LIMIT",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": self._instruction(signal, asset_type),
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": asset_type,
                    },
                }
            ],
        }
        if not is_market:
            price = signal.limit_price
            if price is None and signal.legs:
                price = signal.legs[0].limit_price
            if price is None:
                raise ValueError("Schwab 限价单缺少 limit_price")
            payload["price"] = self._decimal_text(float(price))
        return payload

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        if not self.connected and not self.connect():
            return {
                "order_id": None,
                "status": "FAILED",
                "error": self.connect_error or "Schwab 未连接",
            }
        try:
            response = self._request(
                "POST",
                f"/accounts/{self.account_hash}/orders",
                json=self._order_payload(signal),
                headers={"Content-Type": "application/json"},
            )
            location = response.headers.get("Location") or response.headers.get("location") or ""
            order_id = location.rstrip("/").split("/")[-1] if location else ""
            if not order_id:
                body = response.json() if response.content else {}
                order_id = str(body.get("orderId") or body.get("order_id") or "")
            if not order_id:
                raise RuntimeError("Schwab 下单成功但响应未包含订单 ID")
            return {"order_id": order_id, "status": "SUCCESS", "error": None}
        except Exception as exc:
            error = self._error_detail(exc)
            logger.exception("Schwab 下单失败: %s", error)
            return {"order_id": None, "status": "FAILED", "error": error}

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._request(
                "DELETE",
                f"/accounts/{self.account_hash}/orders/{order_id}",
            )
            return True
        except Exception as exc:
            logger.error("Schwab 撤单失败 order_id=%s: %s", order_id, self._error_detail(exc))
            return False

    @staticmethod
    def _fill_details(row: Dict[str, Any]) -> tuple[float, Optional[float]]:
        filled_quantity = float(row.get("filledQuantity") or 0)
        executions: List[Dict[str, Any]] = []
        for activity in row.get("orderActivityCollection") or []:
            executions.extend(activity.get("executionLegs") or [])
        if not executions:
            return filled_quantity, None
        total_quantity = sum(
            (Decimal(str(item.get("quantity") or 0)) for item in executions),
            Decimal("0"),
        )
        total_value = sum(
            (
                Decimal(str(item.get("quantity") or 0))
                * Decimal(str(item.get("price") or 0))
                for item in executions
            ),
            Decimal("0"),
        )
        average_price = float(total_value / total_quantity) if total_quantity > 0 else None
        return filled_quantity or float(total_quantity), average_price

    @classmethod
    def _normalize_order(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        raw_status = str(row.get("status") or "")
        standard = SchwabStatusMapper.to_standard(raw_status)
        filled_quantity, fill_price = cls._fill_details(row)
        requested_quantity = float(row.get("quantity") or 0)
        if (
            standard == OrderStatus.SUBMITTED
            and filled_quantity > 0
            and (requested_quantity <= 0 or filled_quantity < requested_quantity)
        ):
            standard = OrderStatus.PARTIALLY_FILLED
        legs = row.get("orderLegCollection") or []
        first_leg = legs[0] if legs else {}
        instrument = first_leg.get("instrument") or {}
        return {
            "order_id": str(row.get("orderId") or ""),
            "symbol": instrument.get("symbol") or "",
            "status": standard.value,
            "order_status": standard.value,
            "broker_status": raw_status,
            "quantity": int(float(row.get("quantity") or first_leg.get("quantity") or 0)),
            "filled_quantity": filled_quantity,
            "filled_qty": filled_quantity,
            "fill_price": fill_price,
            "filled_price": fill_price,
            "limit_price": float(row.get("price") or 0),
            "action": first_leg.get("instruction") or "",
        }

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        try:
            response = self._request(
                "GET",
                f"/accounts/{self.account_hash}/orders/{order_id}",
            )
            return self._normalize_order(response.json())
        except Exception as exc:
            logger.warning("Schwab 查询订单失败 order_id=%s: %s", order_id, self._error_detail(exc))
            return None

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        try:
            response = self._request(
                "GET",
                f"/accounts/{self.account_hash}/orders",
                params={
                    "fromEnteredTime": (now - timedelta(days=1)).isoformat().replace("+00:00", "Z"),
                    "toEnteredTime": (now + timedelta(minutes=1)).isoformat().replace("+00:00", "Z"),
                    "maxResults": 100,
                },
            )
            orders = [self._normalize_order(row) for row in response.json()]
            if status:
                target = status.upper()
                orders = [row for row in orders if row["status"].upper() == target]
            return orders
        except Exception as exc:
            logger.error("Schwab 查询订单列表失败: %s", self._error_detail(exc))
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
