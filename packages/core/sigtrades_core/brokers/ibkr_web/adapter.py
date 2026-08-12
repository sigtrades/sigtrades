"""IBKR Web API 适配器（First Party OAuth，云端执行）。

与本地 TWS `ibkr` 适配器并存：本适配器走 api.ibkr.com REST，不依赖 TWS/Agent。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.brokers.ibkr_web.oauth import IbkrWebOAuth
from sigtrades_core.brokers.status_mapping import map_ibkr_status
from sigtrades_core.signal.models import Signal
from sigtrades_core.signal.option_symbol import parse_option_symbol
from sigtrades_core.trading.order_status import OrderStatus

logger = logging.getLogger(__name__)


class IbkrWebBrokerAdapter(BaseBrokerAdapter):
    """IBKR Client Portal / Web API（OAuth First Party）。"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.account_id = (
            config.get("account_id") or config.get("account") or config.get("acctId") or ""
        ).strip()
        self.env = (config.get("env") or "paper").strip().lower()
        self._oauth = IbkrWebOAuth(config)
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)
        self._selected_account: Optional[str] = None

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def connect(self) -> bool:
        self.connect_error = None
        self.connected = False
        err = self._oauth.validate_config()
        if err:
            self.connect_error = err
            return False
        try:
            self._oauth.ensure_lst(self._raw_http)
            # tickle → session cookie
            tickle = self._api("GET", "/tickle")
            cookie = None
            if isinstance(tickle, dict):
                cookie = (
                    tickle.get("session")
                    or (tickle.get("ssoExpires") and None)
                    or tickle.get("sessionId")
                )
            # httpx cookie jar
            api_cookie = self._client.cookies.get("api")
            if api_cookie:
                self._oauth.set_api_cookie(api_cookie)
            elif cookie:
                self._oauth.set_api_cookie(str(cookie))

            init = self._api(
                "POST",
                "/iserver/auth/ssodh/init",
                json_body={"publish": True, "compete": True},
            )
            if isinstance(init, dict) and init.get("authenticated") is False:
                raise RuntimeError(
                    f"经纪会话初始化失败: {init}. 请关闭其他 IBKR 会话（TWS/网页）后重试"
                )

            accounts = self._api("GET", "/iserver/accounts")
            acct = self._pick_account(accounts)
            if not acct:
                raise RuntimeError("未找到可用 IBKR 账户，请在凭证中填写 account_id")
            self._selected_account = acct
            # 切换账户（多账户时）
            try:
                self._api("POST", "/iserver/account", json_body={"acctId": acct})
            except Exception:  # noqa: BLE001
                logger.debug("切换账户请求忽略", exc_info=True)
            self.connected = True
            return True
        except Exception as exc:  # noqa: BLE001
            self.connect_error = self._error_detail(exc)
            logger.exception("IBKR Web API 连接失败: %s", self.connect_error)
            return False

    def disconnect(self) -> bool:
        try:
            self._client.close()
        except Exception:  # noqa: BLE001
            pass
        self.connected = False
        return True

    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected and not self.connect():
            raise RuntimeError(self.connect_error or "未连接")
        acct = self._selected_account or self.account_id
        summary: Dict[str, Any] = {
            "account_id": acct,
            "env": self.env,
            "is_paper": self.env in ("paper", "test", "sandbox"),
        }
        try:
            pnl = self._api("GET", "/iserver/account/pnl/partitioned")
            if isinstance(pnl, dict):
                upnl = pnl.get("upnl") or {}
                # 结构因账户类型略有差异
                if isinstance(upnl, dict):
                    first = next(iter(upnl.values()), {}) if upnl else {}
                    if isinstance(first, dict):
                        summary["net_liquidation"] = first.get("nl") or first.get("netliq")
                        summary["available_cash"] = first.get("availablefunds") or first.get("cash")
        except Exception:  # noqa: BLE001
            logger.debug("pnl 拉取失败，继续用账户列表", exc_info=True)
        try:
            accounts = self._api("GET", "/portfolio/accounts")
            if isinstance(accounts, list):
                for row in accounts:
                    if str(row.get("id") or row.get("accountId") or "") == acct:
                        summary["currency"] = row.get("currency") or "USD"
                        break
        except Exception:  # noqa: BLE001
            pass
        return summary

    def get_option_positions(self) -> List[Dict[str, Any]]:
        if not self.connected and not self.connect():
            return []
        acct = self._selected_account or self.account_id
        try:
            rows = self._api("GET", f"/portfolio/{acct}/positions/0")
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(rows, list):
            return []
        out = []
        for row in rows:
            asset = str(row.get("assetClass") or row.get("asset_class") or "").upper()
            if asset in ("OPT", "OPTION", "FOP"):
                out.append(row)
        return out

    def supports_combined_order(self) -> bool:
        # 多腿先走 TWS Agent；Web API combo 后续再开
        return False

    # ------------------------------------------------------------------
    # 下单 / 查单 / 撤单
    # ------------------------------------------------------------------
    def place_order(self, signal: Signal) -> Dict[str, Any]:
        if not self.connected and not self.connect():
            return {
                "order_id": None,
                "status": "FAILED",
                "error": self.connect_error or "IBKR Web API 未连接",
            }
        if signal.legs and len(signal.legs) > 1:
            return {
                "order_id": None,
                "status": "FAILED",
                "error": "IBKR Web API 暂不支持多腿组合，请改用 IBKR TWS Agent",
                "retryable": False,
            }
        try:
            order = self._build_order(signal)
            acct = self._selected_account or self.account_id
            raw = self._api(
                "POST",
                f"/iserver/account/{acct}/orders",
                json_body={"orders": [order]},
            )
            raw = self._confirm_replies(raw)
            order_id = self._extract_order_id(raw)
            if not order_id:
                return {
                    "order_id": None,
                    "status": "FAILED",
                    "error": f"下单响应无 order_id: {raw!r}"[:500],
                }
            return {"order_id": str(order_id), "status": "SUCCESS", "error": None}
        except Exception as exc:  # noqa: BLE001
            err = self._error_detail(exc)
            logger.exception("IBKR Web API 下单失败: %s", err)
            return {"order_id": None, "status": "FAILED", "error": err}

    def cancel_order(self, order_id: str) -> bool:
        if not order_id:
            return False
        acct = self._selected_account or self.account_id
        try:
            if not self.connected and not self.connect():
                return False
            self._api("DELETE", f"/iserver/account/{acct}/order/{order_id}")
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("IBKR Web API 撤单失败 %s: %s", order_id, self._error_detail(exc))
            return False

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        if not order_id:
            return None
        try:
            if not self.connected and not self.connect():
                return None
            row = self._api("GET", f"/iserver/account/order/status/{order_id}")
            if isinstance(row, dict):
                return self._normalize_order(row)
        except Exception:  # noqa: BLE001
            logger.debug("get_order status 失败，回退列表", exc_info=True)
        for od in self.get_orders():
            if str(od.get("order_id") or "") == str(order_id):
                return od
        return None

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            if not self.connected and not self.connect():
                return []
            rows = self._api("GET", "/iserver/account/orders")
            orders = []
            if isinstance(rows, dict):
                orders = rows.get("orders") or []
            elif isinstance(rows, list):
                orders = rows
            out = [self._normalize_order(r) for r in orders if isinstance(r, dict)]
            if status:
                want = status.upper()
                out = [o for o in out if str(o.get("std_status") or "").upper() == want]
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("IBKR Web API get_orders 失败: %s", self._error_detail(exc))
            return []

    # ------------------------------------------------------------------
    # 内部：合约 / 订单体
    # ------------------------------------------------------------------
    def _build_order(self, signal: Signal) -> Dict[str, Any]:
        acct = self._selected_account or self.account_id
        order_type = (signal.order_type or "LMT").upper()
        is_mkt = order_type in ("MKT", "MARKET")
        side = "SELL" if (signal.action or "BUY").upper().startswith("SELL") else "BUY"
        tif = "GTC" if (signal.time_in_force or "DAY").upper() in ("GTC", "GOOD_TIL_CANCELED") else "DAY"
        qty = max(1, int(signal.quantity or 1))
        conid = self._resolve_conid(signal)
        body: Dict[str, Any] = {
            "acctId": acct,
            "conid": int(conid),
            "orderType": "MKT" if is_mkt else "LMT",
            "side": side,
            "tif": tif,
            "quantity": qty,
            "outsideRTH": False,
        }
        if not is_mkt:
            price = signal.limit_price
            if price is None and signal.legs:
                price = signal.legs[0].limit_price
            if price is None:
                raise ValueError("限价单缺少 limit_price")
            body["price"] = float(price)
        return body

    def _resolve_conid(self, signal: Signal) -> int:
        metadata = signal.metadata or {}
        if metadata.get("conid"):
            return int(metadata["conid"])
        asset = (signal.asset_class or "").upper()
        is_option = (
            asset in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS")
            or bool(metadata.get("strike"))
            or bool(signal.legs)
        )
        if not is_option:
            symbol = (signal.symbol or metadata.get("underlying") or "").strip().upper()
            if not symbol:
                raise ValueError("股票订单缺少 symbol")
            return self._search_stock_conid(symbol)

        parsed = parse_option_symbol(
            signal.symbol,
            metadata=metadata,
            underlying=metadata.get("underlying"),
            strike=metadata.get("strike"),
            right=metadata.get("right") or metadata.get("option_type"),
            expiry=metadata.get("expiry") or metadata.get("expiry_date"),
        )
        und = parsed["underlying"]
        strike = float(parsed["strike"])
        right = "C" if str(parsed["right"]).upper().startswith("C") else "P"
        expiry = str(parsed["expiry_contract"])  # YYYYMMDD
        month = expiry[:6]  # YYYYMM
        und_conid = self._search_stock_conid(und)
        info = self._api(
            "GET",
            "/iserver/secdef/info",
            query={
                "conid": und_conid,
                "sectype": "OPT",
                "month": month,
                "strike": strike,
                "right": right,
            },
        )
        rows = info if isinstance(info, list) else []
        for row in rows:
            # 精确匹配到期日
            mat = str(row.get("maturityDate") or row.get("maturity_date") or "").replace("-", "")
            if mat and mat != expiry and not mat.endswith(expiry[2:]):
                continue
            cid = row.get("conid")
            if cid:
                return int(cid)
        if rows and rows[0].get("conid"):
            return int(rows[0]["conid"])
        raise RuntimeError(
            f"未找到期权合约 conid: {und} {expiry} {strike}{right}"
        )

    def _search_stock_conid(self, symbol: str) -> int:
        data = self._api("GET", "/iserver/secdef/search", query={"symbol": symbol})
        if not isinstance(data, list) or not data:
            raise RuntimeError(f"secdef/search 无结果: {symbol}")
        for row in data:
            sections = row.get("sections") or []
            # 优先 STK
            if any(str(s.get("secType") or "").upper() == "STK" for s in sections) or str(
                row.get("symbol") or ""
            ).upper() == symbol.upper():
                cid = row.get("conid")
                if cid:
                    return int(cid)
        cid = data[0].get("conid")
        if not cid:
            raise RuntimeError(f"secdef/search 无 conid: {symbol}")
        return int(cid)

    def _confirm_replies(self, payload: Any, depth: int = 0) -> Any:
        """处理下单确认问答（message / id → /iserver/reply）。"""
        if depth > 5:
            return payload
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            reply_id = item.get("id")
            message = item.get("message")
            if reply_id and message is not None:
                logger.info("IBKR Web API 确认问答 reply_id=%s", reply_id)
                time.sleep(0.3)
                nxt = self._api(
                    "POST",
                    f"/iserver/reply/{reply_id}",
                    json_body={"confirmed": True},
                )
                return self._confirm_replies(nxt, depth + 1)
        return payload

    @staticmethod
    def _extract_order_id(payload: Any) -> Optional[str]:
        items = payload if isinstance(payload, list) else [payload]
        for item in items:
            if not isinstance(item, dict):
                continue
            for key in ("order_id", "orderId", "id"):
                val = item.get(key)
                if val is not None and str(val).isdigit():
                    return str(val)
            # 有时在 order_status 里
            od = item.get("order_status") or item.get("order")
            if isinstance(od, dict):
                for key in ("order_id", "orderId", "id"):
                    val = od.get(key)
                    if val is not None:
                        return str(val)
        return None

    def _normalize_order(self, row: Dict[str, Any]) -> Dict[str, Any]:
        oid = row.get("orderId") or row.get("order_id") or row.get("id")
        raw_status = (
            row.get("order_status")
            or row.get("status")
            or row.get("orderStatus")
            or ""
        )
        std = map_ibkr_status(raw_status)
        filled = row.get("filledQuantity") or row.get("filled") or row.get("cum_fill") or 0
        avg = row.get("avgPrice") or row.get("average_price") or row.get("price")
        return {
            "order_id": str(oid) if oid is not None else "",
            "status": std.value if isinstance(std, OrderStatus) else str(std),
            "std_status": std.value if isinstance(std, OrderStatus) else str(std),
            "filled": filled,
            "filled_quantity": filled,
            "avg_fill_price": avg,
            "fill_price": avg,
            "remaining": row.get("remainingQuantity") or row.get("remaining"),
            "broker_status": raw_status,
        }

    def _pick_account(self, accounts: Any) -> Optional[str]:
        preferred = self.account_id
        ids: List[str] = []
        if isinstance(accounts, dict):
            for key in ("accounts", "acctList"):
                val = accounts.get(key)
                if isinstance(val, list):
                    ids.extend(str(x) for x in val)
            selected = accounts.get("selectedAccount")
            if selected:
                ids.insert(0, str(selected))
        elif isinstance(accounts, list):
            for row in accounts:
                if isinstance(row, str):
                    ids.append(row)
                elif isinstance(row, dict):
                    aid = row.get("id") or row.get("accountId") or row.get("account")
                    if aid:
                        ids.append(str(aid))
        ids = [x for x in ids if x]
        if preferred:
            for x in ids:
                if x == preferred or x.endswith(preferred) or preferred.endswith(x):
                    return x
            # 用户指定了账户号但列表暂未含 —— 仍尝试使用
            return preferred
        return ids[0] if ids else None

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------
    def _raw_http(self, method: str, url: str, headers: Dict[str, str]):
        return self._client.request(method, url, headers=headers)

    def _api(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        json_body: Any = None,
    ) -> Any:
        self._oauth.ensure_lst(self._raw_http)
        headers = self._oauth.auth_headers(method, path, query=query)
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        url = f"{self._oauth.base_url}{path}"
        resp = self._client.request(method, url, headers=headers, params=query, json=json_body)
        # 刷新 cookie
        api_cookie = self._client.cookies.get("api")
        if api_cookie:
            self._oauth.set_api_cookie(api_cookie)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {"raw": resp.text}

    @staticmethod
    def _error_detail(exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            try:
                return f"{exc.response.status_code}: {exc.response.text[:400]}"
            except Exception:  # noqa: BLE001
                return str(exc)
        return str(exc) or exc.__class__.__name__
