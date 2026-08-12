#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""长桥证券 OpenAPI 适配器（云端执行）。"""

from __future__ import annotations

import logging
import re
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.brokers.status_mapping import LongbridgeStatusMapper
from sigtrades_core.signal.models import Signal
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_longbridge_option_symbol,
    format_longbridge_stock_symbol,
    parse_option_symbol,
)

logger = logging.getLogger(__name__)

try:
    from longbridge.openapi import (
        Config,
        OrderSide,
        OrderType,
        OutsideRTH,
        QuoteContext,
        TimeInForceType,
        TradeContext,
    )
except ImportError as e:
    logger.warning("无法导入 longbridge SDK: %s", e)
    Config = None
    TradeContext = None
    QuoteContext = None
    OrderType = None
    OrderSide = None
    TimeInForceType = None
    OutsideRTH = None

_LB_OPTION_TAIL = re.compile(r"^[A-Z][A-Z0-9]*\d{6}[CP]\d+\.[A-Z]+$", re.I)


class LongbridgeBrokerAdapter(BaseBrokerAdapter):
    """长桥 OpenAPI 适配器。"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.app_key = (config.get("app_key") or "").strip()
        self.app_secret = (config.get("app_secret") or "").strip()
        self.access_token = (config.get("access_token") or "").strip()
        self.env = (config.get("env") or "sandbox").strip().lower()
        self.http_url = config.get("http_url")
        self.trade_ctx: Any = None
        self.quote_ctx: Any = None
        self._lb_config: Any = None

    def _build_config(self) -> Any:
        if not Config:
            raise RuntimeError("longbridge SDK 未安装")
        if not self.app_key or not self.app_secret or not self.access_token:
            raise ValueError("longbridge 需提供 app_key、app_secret、access_token")
        kwargs: Dict[str, Any] = {}
        if self.http_url:
            kwargs["http_url"] = self.http_url
        return Config.from_apikey(
            self.app_key,
            self.app_secret,
            self.access_token,
            **kwargs,
        )

    def connect(self) -> bool:
        self.connect_error = None
        try:
            if not TradeContext:
                self.connect_error = "longbridge SDK 未安装"
                logger.error(self.connect_error)
                return False
            if not self.app_key or not self.app_secret or not self.access_token:
                self.connect_error = (
                    "长桥凭证不完整：请检查 App Key、App Secret、Access Token 是否已正确保存"
                )
                logger.error(self.connect_error)
                return False
            self._lb_config = self._build_config()
            self.trade_ctx = TradeContext(self._lb_config)
            balances = self.trade_ctx.account_balance()
            if balances is None:
                self.connect_error = "长桥 account_balance 返回 None，请确认 Access Token 未过期且账号已开通 OpenAPI"
                logger.warning("长桥连接测试失败：account_balance 为 None env=%s", self.env)
                return False
            logger.info(
                "长桥 API 连接成功 env=%s accounts=%s",
                self.env,
                len(balances),
            )
            self.connected = True
            return True
        except Exception as e:
            self.connect_error = str(e)
            logger.exception("长桥连接失败: %s", e)
            self.connected = False
            return False

    def disconnect(self) -> bool:
        self.trade_ctx = None
        self.quote_ctx = None
        self._lb_config = None
        self.connected = False
        return True

    def _ensure_quote_ctx(self) -> Any:
        if not QuoteContext:
            raise RuntimeError("longbridge SDK 未安装")
        if not self._lb_config:
            self._lb_config = self._build_config()
        if self.quote_ctx is None:
            self.quote_ctx = QuoteContext(self._lb_config)
        return self.quote_ctx

    def _lookup_option_symbol_from_chain(self, parsed: ParsedOption) -> Optional[str]:
        """从长桥期权链 API 获取官方 call_symbol / put_symbol。"""
        try:
            ctx = self._ensure_quote_ctx()
            underlying = format_longbridge_stock_symbol(parsed.underlying)
            expiry = parsed.expiry_contract  # YYYYMMDD
            chain = ctx.option_chain_info_by_date(underlying, expiry) or []
            target = float(parsed.strike)
            right = parsed.right.upper()
            for row in chain:
                try:
                    price = float(getattr(row, "price", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if abs(price - target) > 0.001:
                    continue
                sym = (
                    getattr(row, "call_symbol", None)
                    if right == "C"
                    else getattr(row, "put_symbol", None)
                )
                if sym:
                    return str(sym)
            logger.warning(
                "长桥期权链未找到匹配合约 underlying=%s expiry=%s strike=%s right=%s",
                underlying,
                expiry,
                target,
                right,
            )
        except Exception as e:
            logger.warning("长桥期权链查询失败: %s", e)
        return None

    def _should_use_option_chain(self) -> bool:
        """模拟/无行情权限时不查期权链（下单仍可用本地 symbol 格式）。"""
        explicit = self.config.get("use_option_chain")
        if explicit is not None:
            return bool(explicit)
        return self.env not in ("sandbox", "test", "offline", "paper", "simulate")

    def _resolve_lb_option_symbol(self, parsed: ParsedOption) -> str:
        """优先期权链官方代码，失败则本地拼接（无 OCC 前导零）。"""
        fallback = format_longbridge_option_symbol(parsed)
        if not self._should_use_option_chain():
            logger.debug("长桥 env=%s 跳过期权链查询，使用本地 symbol: %s", self.env, fallback)
            return fallback
        resolved = self._lookup_option_symbol_from_chain(parsed)
        if resolved and resolved != fallback:
            logger.info("长桥期权 symbol 解析: %s → %s", fallback, resolved)
            return resolved
        if resolved:
            return resolved
        return fallback

    def get_account_info(self) -> Dict[str, Any]:
        if not self.trade_ctx:
            raise RuntimeError("长桥未连接")
        balances = self.trade_ctx.account_balance() or []
        out: List[Dict[str, Any]] = []
        for b in balances:
            out.append({
                "currency": getattr(b, "currency", None),
                "total_cash": float(getattr(b, "total_cash", 0) or 0),
                "net_assets": float(getattr(b, "net_assets", 0) or 0),
                "buy_power": float(getattr(b, "buy_power", 0) or 0),
            })
        return {"balances": out, "env": self.env}

    def get_option_positions(self) -> List[Dict[str, Any]]:
        if not self.trade_ctx:
            raise RuntimeError("长桥未连接")
        positions = self.trade_ctx.stock_positions() or []
        opts: List[Dict[str, Any]] = []
        for p in positions:
            sym = str(getattr(p, "symbol", "") or "")
            if not _LB_OPTION_TAIL.match(sym.replace(" ", "")):
                continue
            opts.append({
                "symbol": sym,
                "quantity": int(float(getattr(p, "quantity", 0) or 0)),
                "available_quantity": int(float(getattr(p, "available_quantity", 0) or 0)),
                "cost_price": float(getattr(p, "cost_price", 0) or 0),
                "currency": getattr(p, "currency", None),
            })
        return opts

    def supports_combined_order(self) -> bool:
        # 长桥 OpenAPI 仅支持单标的下单，无 mleg/组合腿接口
        return False

    @staticmethod
    def _is_multi_leg_signal(signal: Signal) -> bool:
        legs = list(signal.legs or [])
        if len(legs) > 1:
            return True
        action = (signal.action or "").strip().upper()
        return action in ("组合", "COMBO", "MLEG", "MULTI", "MULTILEG")

    def _resolve_lb_symbol(self, signal: Signal) -> str:
        ac = (signal.asset_class or "").upper()
        meta = signal.metadata or {}
        if ac in ("OPTIONS", "STOCK_OPTIONS", "SPX_OPTIONS") or meta.get("strike"):
            info = parse_option_symbol(
                signal.symbol,
                metadata=meta,
                underlying=meta.get("underlying"),
                strike=meta.get("strike"),
                right=meta.get("right") or meta.get("option_type"),
                expiry=meta.get("expiry") or meta.get("expiry_date"),
            )
            return self._resolve_lb_option_symbol(
                ParsedOption(
                    underlying=info["underlying"],
                    strike=float(info["strike"]),
                    right=info["right"],
                    put_call=info["put_call"],
                    expiry=info["expiry"],
                    expiry_contract=info["expiry_contract"],
                )
            )
        return format_longbridge_stock_symbol(signal.symbol or meta.get("underlying") or "")

    def _map_side(self, action: str) -> Any:
        act = (action or "BUY").strip().upper()
        if OrderSide is None:
            raise RuntimeError("longbridge SDK 未安装")
        return OrderSide.Sell if act == "SELL" else OrderSide.Buy

    def _map_order_type(self, signal: Signal) -> Any:
        if OrderType is None:
            raise RuntimeError("longbridge SDK 未安装")
        return OrderType.MO if (signal.order_type or "LMT").upper() == "MKT" else OrderType.LO

    def _map_time_in_force(self, signal: Signal) -> Any:
        if TimeInForceType is None:
            raise RuntimeError("longbridge SDK 未安装")
        tif = (signal.time_in_force or "DAY").strip().upper()
        if tif in ("GTC", "GOOD_TIL_CANCELED"):
            return TimeInForceType.GoodTilCanceled
        return TimeInForceType.Day

    def _outside_rth(self, lb_symbol: str) -> Optional[Any]:
        if OutsideRTH is None or not lb_symbol.upper().endswith(".US"):
            return None
        return OutsideRTH.AnyTime

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        if not self.trade_ctx:
            if not self.connect():
                return {
                    "order_id": None,
                    "status": "FAILED",
                    "retryable": False,
                    "error": "长桥未连接",
                }

        # 多腿组合不可交易：若继续下单，normalize 会把 symbol 改成第一腿并误用 Buy，造成错误重试
        if self._is_multi_leg_signal(signal):
            err = (
                "长桥不支持多腿组合单（如 PCS/垂直价差）。"
                "请改用 Alpaca、IBKR 或富途，或改为单腿信号。"
            )
            logger.error("长桥拒绝多腿信号 signal_id=%s legs=%s", signal.signal_id, len(signal.legs or []))
            return {"order_id": None, "status": "FAILED", "retryable": False, "error": err}

        try:
            lb_symbol = self._resolve_lb_symbol(signal)
            quantity = max(1, int(signal.quantity or 1))
            order_type = self._map_order_type(signal)
            side = self._map_side(signal.action)
            tif = self._map_time_in_force(signal)

            kwargs: Dict[str, Any] = {
                "symbol": lb_symbol,
                "order_type": order_type,
                "side": side,
                "submitted_quantity": Decimal(quantity),
                "time_in_force": tif,
                "remark": (signal.signal_id or "")[:64],
            }
            outside = self._outside_rth(lb_symbol)
            if outside is not None:
                kwargs["outside_rth"] = outside

            if order_type == OrderType.LO:
                px = signal.limit_price
                if px is None and signal.legs and signal.legs[0].limit_price is not None:
                    px = signal.legs[0].limit_price
                if px is None:
                    raise ValueError("限价单缺少 limit_price")
                kwargs["submitted_price"] = Decimal(str(px))

            logger.info(
                "长桥下单: %s %s x%s type=%s tif=%s",
                side,
                lb_symbol,
                quantity,
                order_type,
                tif,
            )
            resp = self.trade_ctx.submit_order(**kwargs)
            order_id = getattr(resp, "order_id", None) or str(resp)
            return {"order_id": str(order_id), "status": "SUCCESS", "error": None}
        except Exception as e:
            logger.exception("长桥下单失败: %s", e)
            return {"order_id": None, "status": "FAILED", "error": str(e)}

    def cancel_order(self, order_id: str) -> bool:
        if not self.trade_ctx:
            return False
        try:
            self.trade_ctx.cancel_order(str(order_id))
            return True
        except Exception as e:
            logger.error("长桥撤单失败 order_id=%s: %s", order_id, e)
            return False

    @staticmethod
    def _normalize_order_row(row: Any) -> Dict[str, Any]:
        std = LongbridgeStatusMapper.to_standard(getattr(row, "status", None))
        executed_qty = int(float(getattr(row, "executed_quantity", 0) or 0))
        executed_price = float(getattr(row, "executed_price", 0) or 0)
        if executed_qty > 0 and executed_price <= 0:
            executed_price = float(getattr(row, "last_done", 0) or 0)
        return {
            "order_id": str(getattr(row, "order_id", "") or ""),
            "symbol": getattr(row, "symbol", ""),
            "status": std.value,
            "order_status": std.value,
            "broker_status": str(getattr(row, "status", "") or ""),
            "quantity": int(float(getattr(row, "quantity", 0) or getattr(row, "submitted_quantity", 0) or 0)),
            "filled_quantity": executed_qty,
            "filled_qty": executed_qty,
            "fill_price": executed_price if executed_qty > 0 else None,
            "filled_price": executed_price if executed_qty > 0 else None,
            "limit_price": float(getattr(row, "price", 0) or getattr(row, "submitted_price", 0) or 0),
            "action": str(getattr(row, "side", "") or ""),
        }

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """按订单 ID 查询详情（长桥 order_detail API）。"""
        if not self.trade_ctx:
            return None
        try:
            row = self.trade_ctx.order_detail(str(order_id))
            if row is None:
                return None
            return self._normalize_order_row(row)
        except Exception as e:
            logger.warning("长桥 order_detail 失败 order_id=%s: %s", order_id, e)
            return None

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        if not self.trade_ctx:
            return []
        try:
            rows = self.trade_ctx.today_orders() or []
        except Exception as e:
            logger.error("长桥查询当日订单失败: %s", e)
            return []

        out: List[Dict[str, Any]] = []
        for row in rows:
            item = self._normalize_order_row(row)
            if status and item["status"].lower() != status.lower():
                continue
            out.append(item)
        return out
