"""uSMART（盈立）Open API 适配器 — 云端 REST。

官方 Demo：openapi-sg-demo-py
- 我的 API：X-Channel + 公钥 + 私钥
- 生产交易：https://open-jy.usmartsg.com
- 交易签名：MD5withRSA + 标准 Base64（非 URL-safe）
文档：https://api-doc.usmart.sg/zh-cn/trade.html
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.brokers.status_mapping import UsmartStatusMapper
from sigtrades_core.brokers.usmart.crypto import (
    gen_request_id,
    gen_unix_time,
    load_private_key,
    load_public_key,
    rsa_encrypt_urlsafe,
    sign_md5_with_rsa_b64,
)
from sigtrades_core.signal.models import Signal
from sigtrades_core.trading.order_status import OrderStatus

logger = logging.getLogger(__name__)

# 与官方 openapi-sg-demo-py README / config 一致
_HOSTS = {
    "sg": {
        "live": "https://open-jy.usmartsg.com",
        "uat": "https://open-jy-uat.usmartsg.com",
    },
    # 文档示例仍见 yxzq.com；HK 申请主体默认走同一 Open API 网关时可覆盖 trade_host
    "hk": {
        "live": "https://open-jy.usmartsg.com",
        "uat": "https://open-jy-uat.usmartsg.com",
    },
}

_PATH_LOGIN = "/user-server-sg/open-api/login"
_PATH_TRADE_LOGIN = "/user-server-sg/open-api/trade-login"
_PATH_ENTRUST = "/order-center-sg/open-api/entrust-order"
_PATH_MODIFY = "/order-center-sg/open-api/modify-order"
_PATH_TODAY = "/order-center-sg/open-api/today-entrust"
_PATH_ASSET = "/asset-center-sg/open-api/stock-asset"


class UsmartBrokerAdapter(BaseBrokerAdapter):
    """盈立 uSMART Open API（云端）。"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.channel = str(config.get("channel") or config.get("X_Channel") or "").strip()
        self.phone_number = str(config.get("phone_number") or config.get("phoneNumber") or "").strip()
        self.login_password = str(
            config.get("login_password") or config.get("password") or ""
        ).strip()
        self.trade_password = str(
            config.get("trade_password") or config.get("trade_passwrod") or ""
        ).strip()
        self.public_key_pem = str(config.get("public_key") or "").strip()
        self.private_key_pem = str(config.get("private_key") or "").strip()
        region_raw = str(config.get("region") or "sg").strip().lower()
        self.region = "hk" if region_raw in ("hk", "hongkong", "hong kong", "香港") else "sg"
        default_area = "852" if self.region == "hk" else "65"
        self.area_code = str(
            config.get("area_code") or config.get("areaCode") or default_area
        ).strip()
        self.lang = str(config.get("lang") or config.get("X_Lang") or "1").strip()
        # 官方 demo conf 里 X-Type=12
        self.x_type = str(config.get("x_type") or config.get("X_Type") or "12").strip()
        env = str(config.get("env") or "live").strip().lower()
        self.env = "uat" if env in ("uat", "test", "sandbox", "paper") else "live"
        default_host = _HOSTS[self.region][self.env]
        self.trade_host = str(config.get("trade_host") or default_host).rstrip("/")
        self.default_exchange = int(config.get("exchange_type") or config.get("exchangeType") or 5)
        self.force_entrust = bool(config.get("force_entrust") or config.get("forceEntrustFlag"))
        self._client = httpx.Client(timeout=30.0)
        self._token: Optional[str] = None
        self._public_key = None
        self._private_key = None
        self.connect_error: Optional[str] = None

    def _load_keys(self) -> None:
        if self._public_key is None:
            self._public_key = load_public_key(self.public_key_pem)
        if self._private_key is None:
            self._private_key = load_private_key(self.private_key_pem)

    def _encrypt(self, plaintext: str) -> str:
        self._load_keys()
        return rsa_encrypt_urlsafe(self._public_key, plaintext)

    def _post(
        self,
        path: str,
        params: Dict[str, Any],
        *,
        need_auth: bool = True,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        self._load_keys()
        # 与官方 demo requests 侧一致：默认 json.dumps 分隔符（含空格）
        body = json.dumps(params, ensure_ascii=False)
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Lang": self.lang,
            "X-Channel": self.channel,
            "X-Sign": sign_md5_with_rsa_b64(self._private_key, body),
            "Authorization": self._token or "",
        }
        if extra_headers:
            headers.update(extra_headers)
        if need_auth and not self._token:
            raise RuntimeError("uSMART 未登录")
        response = self._client.post(
            f"{self.trade_host}{path}",
            content=body.encode("utf-8"),
            headers=headers,
        )
        try:
            payload = response.json()
        except Exception:  # noqa: BLE001
            raise RuntimeError(f"uSMART HTTP {response.status_code}: {response.text[:300]}") from None
        if response.status_code >= 400:
            raise RuntimeError(f"uSMART HTTP {response.status_code}: {payload}")
        return payload if isinstance(payload, dict) else {"code": -1, "data": payload}

    @staticmethod
    def _ok(payload: Dict[str, Any]) -> bool:
        code = payload.get("code")
        return code in (0, "0")

    def _trade_headers(self) -> Dict[str, str]:
        return {
            "X-Type": self.x_type,
            "X-Request-Id": gen_unix_time(16),
        }

    def connect(self) -> bool:
        self.connect_error = None
        self.connected = False
        self._token = None
        missing = [
            name
            for name, val in (
                ("channel", self.channel),
                ("public_key", self.public_key_pem),
                ("private_key", self.private_key_pem),
            )
            if not val
        ]
        if missing:
            self.connect_error = f"uSMART 凭证不完整，缺少: {', '.join(missing)}"
            return False
        # 官方「我的 API」只发渠道号+密钥；login 仍要手机号/密码（见 demo config.json）
        if not (self.phone_number and self.login_password and self.trade_password):
            self.connect_error = (
                "已配置渠道号与 RSA 密钥，但连接账户还需手机号、登录密码与交易密码"
                "（官方 login / trade-login 接口；见 openapi-sg-demo-py）"
            )
            return False
        try:
            login = self._post(
                _PATH_LOGIN,
                {
                    "phoneNumber": self._encrypt(self.phone_number),
                    "password": self._encrypt(self.login_password),
                    "areaCode": self.area_code,
                },
                need_auth=False,
            )
            if not self._ok(login):
                self.connect_error = f"登录失败: {login.get('msg') or login}"
                return False
            data = login.get("data") or {}
            token = data.get("token") if isinstance(data, dict) else None
            if not token:
                self.connect_error = "登录成功但未返回 token"
                return False
            self._token = str(token)

            unlock = self._post(
                _PATH_TRADE_LOGIN,
                {"password": self._encrypt(self.trade_password)},
                extra_headers=self._trade_headers(),
            )
            if not self._ok(unlock):
                self.connect_error = f"交易解锁失败: {unlock.get('msg') or unlock}"
                return False

            asset = self._post(_PATH_ASSET, {}, extra_headers=self._trade_headers())
            if not self._ok(asset):
                self.connect_error = f"查询资产失败: {asset.get('msg') or asset}"
                return False

            self.connected = True
            return True
        except Exception as exc:  # noqa: BLE001
            self.connect_error = str(exc) or type(exc).__name__
            logger.exception("uSMART 连接失败: %s", self.connect_error)
            return False

    def disconnect(self) -> bool:
        self._token = None
        self.connected = False
        if not self._client.is_closed:
            self._client.close()
        return True

    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected and not self.connect():
            raise RuntimeError(self.connect_error or "uSMART 未连接")
        asset = self._post(_PATH_ASSET, {}, extra_headers=self._trade_headers())
        if not self._ok(asset):
            raise RuntimeError(asset.get("msg") or "查询资产失败")
        data = asset.get("data")
        row: Dict[str, Any] = {}
        if isinstance(data, list) and data:
            row = dict(data[0] or {})
        elif isinstance(data, dict):
            nested = data.get("list") or data.get("assetList")
            if isinstance(nested, list) and nested:
                row = dict(nested[0] or {})
            else:
                row = dict(data)
        return {
            "account_id": row.get("fundAccount")
            or row.get("account")
            or self.config.get("account_id")
            or self.phone_number
            or self.channel,
            "net_liquidation": row.get("asset")
            or row.get("totalAsset")
            or row.get("mv")
            or row.get("netAsset"),
            "available_cash": row.get("enableBalance")
            or row.get("cash")
            or row.get("purchasingPower")
            or row.get("marginPurchasePower"),
            "currency": self._money_type_to_ccy(row.get("moneyType")),
            "is_paper": self.env == "uat",
            "env": self.env,
            "raw": row,
        }

    def get_option_positions(self) -> List[Dict[str, Any]]:
        """盈立个人 Open API 以正股为主；期权持仓暂空列表。"""
        return []

    def supports_combined_order(self) -> bool:
        return False

    @staticmethod
    def _money_type_to_ccy(money_type: Any) -> str:
        mapping = {0: "HKD", 1: "USD", 2: "CNY", "0": "HKD", "1": "USD", "2": "CNY"}
        return mapping.get(money_type, "USD")

    def _resolve_exchange_and_code(self, signal: Signal) -> tuple[int, str]:
        raw = (signal.symbol or "").strip()
        if not raw:
            raise ValueError("缺少标的代码")
        # AAPL / AAPL.US → 美股；00700 / 700.HK → 港股
        upper = raw.upper()
        if upper.endswith(".HK") or re.fullmatch(r"\d{1,5}", raw):
            code = re.sub(r"(?i)\.HK$", "", raw).zfill(5)
            return 0, code
        if upper.endswith(".US") or re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", upper):
            code = re.sub(r"(?i)\.US$", "", raw).upper()
            return 5, code
        code = re.sub(r"(?i)\.US$", "", raw).upper()
        return self.default_exchange, code

    def _entrust_prop(self, signal: Signal, *, exchange_type: int) -> str:
        order_type = (signal.order_type or "LMT").upper()
        if order_type in ("MKT", "MARKET"):
            return "w" if exchange_type == 0 else "0"
        return "e" if exchange_type == 0 else "0"

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        if signal.legs and len(signal.legs) > 1:
            return {
                "order_id": None,
                "status": "FAILED",
                "error": "uSMART 暂不支持多腿组合单",
                "retryable": False,
            }
        if not self.connected and not self.connect():
            return {
                "order_id": None,
                "status": "FAILED",
                "error": self.connect_error or "uSMART 未连接",
            }
        try:
            exchange_type, stock_code = self._resolve_exchange_and_code(signal)
            action = (signal.action or "BUY").strip().upper()
            entrust_type = 1 if action.startswith("SELL") else 0
            order_type = (signal.order_type or "LMT").upper()
            is_market = order_type in ("MKT", "MARKET")
            price = 0.0 if is_market else float(signal.limit_price or 0)
            if not is_market and price <= 0:
                raise ValueError("uSMART 限价单缺少 limit_price")
            qty = max(1, int(signal.quantity or 1))
            if is_market and exchange_type == 5:
                raise ValueError("uSMART 美股请使用限价单（LMT）；市价单请改港股或改限价")

            params: Dict[str, Any] = {
                "serialNo": gen_request_id(),
                "stockCode": stock_code,
                "entrustPrice": price,
                "entrustAmount": qty,
                "exchangeType": exchange_type,
                "entrustProp": self._entrust_prop(signal, exchange_type=exchange_type),
                "entrustType": entrust_type,
                "password": self._encrypt(self.trade_password),
                "forceEntrustFlag": self.force_entrust,
            }
            payload = self._post(_PATH_ENTRUST, params, extra_headers=self._trade_headers())
            if not self._ok(payload):
                return {
                    "order_id": None,
                    "status": "FAILED",
                    "error": str(payload.get("msg") or payload),
                }
            data = payload.get("data") or {}
            order_id = str(
                (data.get("entrustId") if isinstance(data, dict) else None)
                or (data.get("serialNo") if isinstance(data, dict) else None)
                or ""
            )
            if not order_id:
                return {
                    "order_id": None,
                    "status": "FAILED",
                    "error": f"下单响应无 entrustId: {payload}",
                }
            return {"order_id": order_id, "status": "SUCCESS", "error": None}
        except Exception as exc:  # noqa: BLE001
            logger.exception("uSMART 下单失败")
            return {"order_id": None, "status": "FAILED", "error": str(exc)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.connected and not self.connect():
            return False
        try:
            payload = self._post(
                _PATH_MODIFY,
                {
                    "actionType": 0,
                    "entrustAmount": 0,
                    "entrustId": int(order_id),
                    "entrustPrice": 0,
                    "forceEntrustFlag": self.force_entrust,
                    "password": self._encrypt(self.trade_password),
                },
                extra_headers=self._trade_headers(),
            )
            return self._ok(payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("uSMART 撤单失败 order_id=%s: %s", order_id, exc)
            return False

    def _normalize_order(self, row: Dict[str, Any]) -> Dict[str, Any]:
        raw_status = row.get("statusName") or row.get("status")
        standard = UsmartStatusMapper.to_standard(raw_status)
        qty = float(row.get("entrustAmount") or 0)
        filled = float(row.get("businessAmount") or 0)
        if standard == OrderStatus.SUBMITTED and 0 < filled < qty:
            standard = OrderStatus.PARTIALLY_FILLED
        fill_price = row.get("businessAveragePrice")
        entrust_type = row.get("entrustType")
        action = "SELL" if str(entrust_type) in ("1", "1.0") else "BUY"
        return {
            "order_id": str(row.get("entrustId") or row.get("serialNo") or ""),
            "symbol": row.get("stockCode") or "",
            "status": standard.value,
            "order_status": standard.value,
            "broker_status": str(raw_status or ""),
            "quantity": int(qty),
            "filled_quantity": filled,
            "filled_qty": filled,
            "fill_price": float(fill_price) if fill_price not in (None, "") else None,
            "filled_price": float(fill_price) if fill_price not in (None, "") else None,
            "limit_price": float(row.get("entrustPrice") or 0),
            "action": action,
        }

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.connected and not self.connect():
            return []
        try:
            payload = self._post(
                _PATH_TODAY,
                {
                    "exchangeType": 100,
                    "pageNum": 1,
                    "pageSize": 50,
                    "stockCode": "",
                },
                extra_headers=self._trade_headers(),
            )
            if not self._ok(payload):
                return []
            data = payload.get("data") or {}
            rows = data.get("list") if isinstance(data, dict) else data
            if not isinstance(rows, list):
                rows = []
            orders = [self._normalize_order(dict(r)) for r in rows if isinstance(r, dict)]
            if status:
                target = status.upper()
                orders = [o for o in orders if o["status"].upper() == target]
            return orders
        except Exception as exc:  # noqa: BLE001
            logger.error("uSMART 查询订单失败: %s", exc)
            return []
