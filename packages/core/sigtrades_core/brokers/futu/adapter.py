#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
富途证券适配器实现
Futu Broker Adapter Implementation
通过 Futu OpenAPI + OpenD 网关进行自动化交易
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from futu import (
        OpenSecTradeContext, OpenQuoteContext,
        TrdSide, TrdEnv, OrderType, OrderStatus as FutuOrderStatus,
        ModifyOrderOp, SecurityFirm, TrdMarket,
        RET_OK, RET_ERROR,
    )
    _futu_imported = True
except ImportError as e:
    logging.warning(f"无法导入 futu 模块: {e}，富途功能不可用")
    _futu_imported = False
    OpenSecTradeContext = None
    OpenQuoteContext = None
    TrdSide = None
    TrdEnv = None
    OrderType = None
    FutuOrderStatus = None
    ModifyOrderOp = None
    SecurityFirm = None
    TrdMarket = None
    RET_OK = 0
    RET_ERROR = -1

# ComboLeg / TimeInForce：futu-api>=10 才有原生组合下单（place_combo_order）
ComboLeg = None
TimeInForce = None
if _futu_imported:
    try:
        from futu import ComboLeg as _ComboLeg  # type: ignore
        ComboLeg = _ComboLeg
    except ImportError:
        try:
            from futu.common.constant import ComboLeg as _ComboLeg  # type: ignore
            ComboLeg = _ComboLeg
        except ImportError:
            ComboLeg = None
    try:
        from futu import TimeInForce as _TimeInForce  # type: ignore
        TimeInForce = _TimeInForce
    except ImportError:
        try:
            from futu.common.constant import TimeInForce as _TimeInForce  # type: ignore
            TimeInForce = _TimeInForce
        except ImportError:
            TimeInForce = None

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.signal.models import Signal, OptionLeg
from sigtrades_core.signal.option_symbol import (
    ParsedOption,
    format_futu_option_code,
    parse_option_symbol,
)
from sigtrades_core.trading.order_status import OrderStatus as StandardOrderStatus

logger = logging.getLogger(__name__)

# 延迟解析时区，避免打包环境缺 tzdata 时整个 adapter 模块导入失败
_NY_TIMEZONE: Optional[ZoneInfo] = None


def _ny_tz() -> ZoneInfo:
    global _NY_TIMEZONE
    if _NY_TIMEZONE is None:
        _NY_TIMEZONE = ZoneInfo("America/New_York")
    return _NY_TIMEZONE

# Futu 订单状态 -> 标准状态
FUTU_STATUS_MAP = {
    "NONE": StandardOrderStatus.UNKNOWN,
    "UNSUBMITTED": StandardOrderStatus.NEW,
    "WAITING_SUBMIT": StandardOrderStatus.NEW,
    "SUBMITTING": StandardOrderStatus.PENDING,
    "SUBMIT_FAILED": StandardOrderStatus.REJECTED,
    "TIMEOUT": StandardOrderStatus.EXPIRED,
    "SUBMITTED": StandardOrderStatus.SUBMITTED,
    "FILLED_PART": StandardOrderStatus.PARTIALLY_FILLED,
    "FILLED_ALL": StandardOrderStatus.FILLED,
    "CANCELLING_PART": StandardOrderStatus.PENDING,
    "CANCELLING_ALL": StandardOrderStatus.PENDING,
    "CANCELLED_PART": StandardOrderStatus.CANCELLED,
    "CANCELLED_ALL": StandardOrderStatus.CANCELLED,
    "FAILED": StandardOrderStatus.REJECTED,
    "DISABLED": StandardOrderStatus.REJECTED,
    "DELETED": StandardOrderStatus.CANCELLED,
}

FUTU_STATUS_CN = {
    "NONE": "未知",
    "UNSUBMITTED": "未提交",
    "WAITING_SUBMIT": "等待提交",
    "SUBMITTING": "提交中",
    "SUBMIT_FAILED": "提交失败",
    "TIMEOUT": "超时",
    "SUBMITTED": "已提交",
    "FILLED_PART": "部分成交",
    "FILLED_ALL": "已成交",
    "CANCELLING_PART": "部分撤销中",
    "CANCELLING_ALL": "撤销中",
    "CANCELLED_PART": "部分已撤销",
    "CANCELLED_ALL": "已撤销",
    "FAILED": "失败",
    "DISABLED": "已禁用",
    "DELETED": "已删除",
}


def _build_futu_option_code(symbol: str, expiry: str, strike: float, right: str) -> str:
    """构建 Futu 格式的美股期权代码。"""
    rt = right if right in ("C", "P") else ("C" if str(right).upper() == "CALL" else "P")
    expiry_full = expiry if len(expiry) == 8 else expiry.replace("-", "")
    parsed = ParsedOption(
        underlying=symbol,
        strike=float(strike),
        right=rt,
        put_call="CALL" if rt == "C" else "PUT",
        expiry=f"{expiry_full[:4]}-{expiry_full[4:6]}-{expiry_full[6:8]}",
        expiry_contract=expiry_full,
    )
    return format_futu_option_code(parsed)


# OpenD server_ver：major*100+minor，如 9.06→906、10.09→1009。
# place_combo_order 需要 OpenD 10.x（与 futu-api>=10 匹配），否则报「未知的协议ID」。
FUTU_MIN_COMBO_SERVER_VER = 1000


def parse_opend_server_ver(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def format_opend_server_ver(server_ver: Optional[int]) -> str:
    if server_ver is None:
        return "未知"
    major, minor = divmod(int(server_ver), 100)
    return f"{major}.{minor:02d}"


def opend_combo_version_warning(server_ver: Optional[int]) -> Optional[str]:
    if server_ver is None:
        return None
    if int(server_ver) >= FUTU_MIN_COMBO_SERVER_VER:
        return None
    return (
        f"OpenD 版本过低（当前 {format_opend_server_ver(server_ver)}，"
        f"组合下单需 ≥{format_opend_server_ver(FUTU_MIN_COMBO_SERVER_VER)}）。"
        "请升级 Futu OpenD 后重启，否则 PCS/垂直价差会因「未知的协议ID」失败。"
    )


class FutuBrokerAdapter(BaseBrokerAdapter):
    """
    富途证券适配器
    
    通过 Futu OpenAPI + OpenD 网关连接富途/moomoo 券商
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化富途适配器
        
        Args:
            config: 券商配置，包含：
                - host: OpenD 地址，默认 127.0.0.1
                - port: OpenD API 端口，默认 11111
                - trd_env: 交易环境 "REAL" 或 "SIMULATE"，默认 SIMULATE
                - security_firm: 券商标识（可选），默认 FUTUSECURITIES
        """
        super().__init__(config)

        if not _futu_imported:
            raise RuntimeError("futu-api 模块未安装，请运行: pip install futu-api")

        self.host = config.get("host", "127.0.0.1")
        self.port = config.get("port", 11111)
        env_str = config.get("trd_env", "SIMULATE").upper()
        self.trd_env = TrdEnv.REAL if env_str == "REAL" else TrdEnv.SIMULATE
        self.security_firm_str = config.get("security_firm", "FUTUSECURITIES")

        self.trd_ctx: Optional[OpenSecTradeContext] = None
        self.acc_id: Optional[int] = None
        self.opend_server_ver: Optional[int] = None
        self.opend_version_warning: Optional[str] = None

    def _refresh_opend_version(self) -> None:
        """连接后读取 OpenD server_ver（get_global_state），供组合能力提示。"""
        self.opend_server_ver = None
        self.opend_version_warning = None
        if not self.trd_ctx or not hasattr(self.trd_ctx, "get_global_state"):
            return
        try:
            ret, data = self.trd_ctx.get_global_state()
            if ret != RET_OK or not isinstance(data, dict):
                return
            self.opend_server_ver = parse_opend_server_ver(data.get("server_ver"))
            self.opend_version_warning = opend_combo_version_warning(self.opend_server_ver)
            logger.info(
                "OpenD server_ver=%s (%s)%s",
                self.opend_server_ver,
                format_opend_server_ver(self.opend_server_ver),
                f" warning={self.opend_version_warning}" if self.opend_version_warning else "",
            )
        except Exception as e:  # noqa: BLE001
            logger.warning("读取 OpenD 版本失败: %s", e)

    def connect(self) -> bool:
        """连接到 OpenD 网关"""
        try:
            security_firm = getattr(SecurityFirm, self.security_firm_str, SecurityFirm.FUTUSECURITIES)
            logger.info(f"正在连接富途 OpenD: {self.host}:{self.port}, env={self.trd_env}, firm={security_firm}")

            self.trd_ctx = OpenSecTradeContext(
                host=self.host,
                port=self.port,
                security_firm=security_firm,
            )

            # 获取账户列表以拿到 acc_id
            ret_acc, acc_data = self.trd_ctx.get_acc_list()
            if ret_acc == RET_OK and acc_data is not None and len(acc_data) > 0:
                logger.info(f"富途账户列表列名: {list(acc_data.columns)}")
                for _, acc_row in acc_data.iterrows():
                    logger.info(f"  账户: {dict(acc_row)}")
                # 根据交易环境筛选账户
                env_val = 'REAL' if self.trd_env == TrdEnv.REAL else 'SIMULATE'
                matched = acc_data[acc_data['trd_env'] == env_val] if 'trd_env' in acc_data.columns else acc_data
                if len(matched) > 0:
                    self.acc_id = int(matched.iloc[0].get("acc_id", 0))
                else:
                    self.acc_id = int(acc_data.iloc[0].get("acc_id", 0))
            else:
                logger.warning(f"获取富途账户列表失败: {acc_data}")

            # 用 accinfo_query 验证连接
            ret, data = self.trd_ctx.accinfo_query(trd_env=self.trd_env)
            if ret != RET_OK:
                logger.error(f"富途连接测试失败: {data}")
                self.connected = False
                return False

            self._refresh_opend_version()
            logger.info(f"富途连接成功，acc_id={self.acc_id}, 环境={'实盘' if self.trd_env == TrdEnv.REAL else '模拟'}")

            self.connected = True
            return True

        except Exception as e:
            logger.error(f"连接富途失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.connected = False
            return False

    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.trd_ctx:
                self.trd_ctx.close()
            self.trd_ctx = None
            self.acc_id = None
            self.connected = False
            logger.info("已断开富途连接")
            return True
        except Exception as e:
            logger.error(f"断开富途连接失败: {e}")
            return False

    @staticmethod
    def _safe_float(val, default=0.0) -> float:
        """安全转换为 float，处理 'N/A'、None 等非数值"""
        if val is None:
            return default
        try:
            f = float(val)
            return f
        except (ValueError, TypeError):
            return default

    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息"""
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        try:
            ret, data = self.trd_ctx.accinfo_query(trd_env=self.trd_env)
            if ret != RET_OK:
                raise RuntimeError(f"查询账户信息失败: {data}")

            if data is None or len(data) == 0:
                return self._empty_account_info()

            row = data.iloc[0]
            sf = self._safe_float

            # 优先使用 USD 专用字段（美股交易场景）
            usd_assets = sf(row.get("usd_assets"))
            us_cash = sf(row.get("us_cash"))

            if usd_assets > 0:
                total = usd_assets
                cash = us_cash
                avl = sf(row.get("us_avl_withdrawal_cash"))
                positions = total - cash
                unrealized = sf(row.get("unrealized_pl"))
                realized = sf(row.get("realized_pl"))
            else:
                total = sf(row.get("total_assets"))
                cash = sf(row.get("cash"))
                avl = sf(row.get("avl_withdrawal_cash"))
                positions = sf(row.get("market_val"))
                unrealized = sf(row.get("unrealized_pl"))
                realized = sf(row.get("realized_pl"))

            logger.info(f"富途账户(USD): total={total}, cash={cash}, positions={positions}")

            return {
                "account": str(self.acc_id or ""),
                "account_id": str(self.acc_id or ""),
                "is_paper": self.trd_env != TrdEnv.REAL,
                "net_liquidation": total,
                "total_assets": total,
                "available_cash": cash,
                "positions_value": positions,
                "equity": total,
                "margin_used": sf(row.get("frozen_cash")),
                "unrealized_pl": unrealized,
                "realized_pl": realized,
            }
        except Exception as e:
            logger.error(f"获取富途账户信息失败: {e}")
            raise

    def _empty_account_info(self) -> Dict[str, Any]:
        return {
            "account": str(self.acc_id or ""),
            "account_id": str(self.acc_id or ""),
            "is_paper": self.trd_env != TrdEnv.REAL,
            "net_liquidation": 0.0, "total_assets": 0.0, "available_cash": 0.0,
            "positions_value": 0.0, "equity": 0.0, "margin_used": 0.0,
            "unrealized_pl": 0.0, "realized_pl": 0.0,
        }

    def get_option_positions(self) -> List[Dict[str, Any]]:
        """获取期权持仓列表"""
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        try:
            ret, data = self.trd_ctx.position_list_query(trd_env=self.trd_env)
            if ret != RET_OK:
                logger.error(f"查询持仓失败: {data}")
                return []

            if data is None or len(data) == 0:
                return []

            result = []
            for _, row in data.iterrows():
                code = str(row.get("code", ""))
                if not code.startswith("US."):
                    continue

                sec_type = str(row.get("sec_type", ""))
                # Futu 对期权 sec_type 可能是 "DRVT" 或含有 option 相关标识
                # 通过代码长度和格式判断是否为期权
                code_without_market = code[3:]  # 去掉 "US."
                is_option = len(code_without_market) > 10  # 期权代码较长

                if not is_option:
                    continue

                quantity = int(self._safe_float(row.get("qty")))
                if quantity == 0:
                    continue

                cost_price = self._safe_float(row.get("cost_price"))

                # 从 Futu code 构建标准期权代码
                try:
                    parsed = self._parse_futu_option_code(code_without_market)
                    symbol = f"{parsed['symbol']}  {parsed['expiry_short']}{parsed['right']}{parsed['strike_str']}"
                    put_call = parsed['put_call']
                    strike = parsed['strike']
                    base_symbol = parsed['symbol']
                    expiry = parsed['expiry']
                except Exception:
                    symbol = code_without_market
                    put_call = 'CALL'
                    strike = 0
                    base_symbol = code_without_market[:4]
                    expiry = ''

                result.append({
                    "symbol": symbol,
                    "type": "Call" if put_call == 'CALL' else "Put",
                    "direction": "买入" if quantity > 0 else "卖出",
                    "quantity": abs(quantity),
                    "cost": f"${cost_price:.2f}",
                    "strike": strike,
                    "put_call": put_call,
                    "base_symbol": base_symbol,
                    "expiry": expiry,
                    "raw_quantity": quantity,
                })

            logger.info(f"获取到 {len(result)} 条富途期权持仓")
            return result

        except Exception as e:
            logger.error(f"获取富途期权持仓失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

    def _parse_futu_option_code(self, code: str) -> Dict[str, Any]:
        """
        解析 Futu 期权代码 (不含 US. 前缀)
        格式: SPXW250519P05910000
        """
        # 找到 C/P 位置
        cp_idx = -1
        for i in range(6, len(code)):
            if code[i] in ('C', 'P'):
                cp_idx = i
                break

        if cp_idx < 0:
            raise ValueError(f"无法解析 Futu 期权代码: {code}")

        symbol = code[:cp_idx - 6]
        expiry_short = code[cp_idx - 6:cp_idx]  # YYMMDD
        right = code[cp_idx]
        strike_str = code[cp_idx + 1:]

        year = '20' + expiry_short[:2]
        month = expiry_short[2:4]
        day = expiry_short[4:6]
        expiry = f"{year}-{month}-{day}"

        strike = float(strike_str.lstrip('0') or '0') / 1000

        return {
            'symbol': symbol,
            'expiry': expiry,
            'expiry_short': expiry_short,
            'right': right,
            'put_call': 'PUT' if right == 'P' else 'CALL',
            'strike': strike,
            'strike_str': strike_str,
        }

    def place_order(self, signal: Signal) -> Dict[str, Any]:
        """
        提交订单。

        多腿组合走 OpenAPI ``place_combo_order``（futu-api>=10），
        见 https://openapi.futunn.com/futu-api-doc/trade/place-combo-order.html
        """
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        from sigtrades_core.brokers.stock_utils import is_stock_signal
        if is_stock_signal(signal):
            symbol = (signal.symbol or "").upper()
            code = symbol if "." in symbol else f"US.{symbol}"
            side = TrdSide.BUY if (signal.action or "BUY").upper() == "BUY" else TrdSide.SELL
            return self._place_single(
                code, side, signal.quantity or 1, signal.order_type or "MKT", signal.limit_price,
            )

        try:
            order_type_str = signal.order_type if signal.order_type else "MKT"
            quantity = signal.quantity or 1

            if quantity <= 0:
                raise ValueError(f"订单数量无效: {quantity}")

            if signal.legs and len(signal.legs) > 1:
                return self._place_combo_order(signal, order_type_str, quantity)
            elif signal.legs and len(signal.legs) == 1:
                leg = signal.legs[0]
                option_info = parse_option_symbol(
                    leg.symbol,
                    metadata=signal.metadata or {},
                    strike=leg.strike,
                    right=leg.option_type,
                )
                futu_code = _build_futu_option_code(
                    option_info['symbol'],
                    option_info['expiry_contract'],
                    option_info['strike'],
                    option_info['right'],
                )
                trd_side = TrdSide.BUY if leg.action == "BUY" else TrdSide.SELL
                return self._place_single(futu_code, trd_side, quantity, order_type_str, signal.limit_price)
            else:
                raise ValueError("订单必须包含腿信息")

        except Exception as e:
            error_msg = f"富途下单失败: {e}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            return {"order_id": None, "status": "FAILED", "error": error_msg}

    def _place_single(self, futu_code: str, trd_side, quantity: int,
                      order_type_str: str, limit_price: Optional[float]) -> Dict[str, Any]:
        """提交单腿订单"""
        if order_type_str == "LMT" and limit_price is not None:
            futu_order_type = OrderType.NORMAL
            price = abs(limit_price)
        else:
            futu_order_type = OrderType.MARKET
            price = 0

        logger.info(f"富途下单: {futu_code}, side={trd_side}, qty={quantity}, "
                     f"type={futu_order_type}, price={price}")

        ret, data = self.trd_ctx.place_order(
            price=price,
            qty=quantity,
            code=futu_code,
            trd_side=trd_side,
            order_type=futu_order_type,
            trd_env=self.trd_env,
        )

        if ret != RET_OK:
            error_msg = f"富途下单失败: {data}"
            logger.error(error_msg)
            return {"order_id": None, "status": "FAILED", "error": error_msg}

        order_id = str(data.iloc[0].get("order_id", "")) if data is not None and len(data) > 0 else ""
        logger.info(f"富途下单成功: order_id={order_id}")
        return {"order_id": order_id, "status": "SUCCESS", "error": None}

    def place_protective_orders(
        self,
        signal: Signal,
        fill_price: float,
        *,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self.connected or not self.trd_ctx:
            return {"status": "skipped"}
        from sigtrades_core.brokers.stock_utils import is_stock_signal

        combo_qty = signal.quantity or 1
        is_long = (signal.action or "BUY").upper() in ("BUY", "OPEN")
        want_protective = stop_loss_pct is not None or take_profit_pct is not None

        def _rollback(order_ids: list[str]) -> None:
            for oid in order_ids:
                if oid:
                    try:
                        self.cancel_order(oid)
                    except Exception:  # noqa: BLE001
                        pass

        def _place_leg_protective(code: str, leg_is_long: bool, leg_fill: float, leg_qty: int) -> list[str]:
            leg_placed: list[str] = []
            exit_side = TrdSide.SELL if leg_is_long else TrdSide.BUY
            if stop_loss_pct is not None and OrderType and hasattr(OrderType, "STOP"):
                stop_px = leg_fill * (1 - stop_loss_pct / 100) if leg_is_long else leg_fill * (1 + stop_loss_pct / 100)
                ret, data = self.trd_ctx.place_order(
                    price=round(stop_px, 2), qty=leg_qty, code=code, trd_side=exit_side,
                    order_type=OrderType.STOP, trd_env=self.trd_env,
                )
                if ret == RET_OK and data is not None and len(data) > 0:
                    leg_placed.append(str(data.iloc[0].get("order_id", "")))
            if take_profit_pct is not None:
                tp_px = leg_fill * (1 + take_profit_pct / 100) if leg_is_long else leg_fill * (1 - take_profit_pct / 100)
                ret, data = self.trd_ctx.place_order(
                    price=round(tp_px, 2), qty=leg_qty, code=code, trd_side=exit_side,
                    order_type=OrderType.NORMAL, trd_env=self.trd_env,
                )
                if ret == RET_OK and data is not None and len(data) > 0:
                    leg_placed.append(str(data.iloc[0].get("order_id", "")))
            return leg_placed

        if is_stock_signal(signal):
            symbol = (signal.symbol or "").upper()
            code = symbol if "." in symbol else f"US.{symbol}"
            placed = _place_leg_protective(code, is_long, fill_price, combo_qty)
            return {"status": "SUCCESS" if placed else "skipped", "order_ids": placed}

        if signal.legs and len(signal.legs) > 1:
            weights = [max(1, leg.quantity or 1) for leg in signal.legs]
            total_w = sum(weights) or 1
            all_placed: list[str] = []
            for leg, w in zip(signal.legs, weights):
                try:
                    option_info = parse_option_symbol(leg.symbol)
                except Exception as e:  # noqa: BLE001
                    _rollback(all_placed)
                    return {"status": "FAILED", "error": f"parse leg failed: {e}", "order_ids": all_placed}
                futu_code = _build_futu_option_code(
                    option_info["symbol"],
                    option_info["expiry_contract"],
                    option_info["strike"],
                    option_info["right"],
                )
                leg_is_long = leg.action.upper() == "BUY"
                leg_qty = leg.quantity or combo_qty
                per_leg_fill = (fill_price * w / total_w) if fill_price else 0.0
                leg_placed = _place_leg_protective(futu_code, leg_is_long, per_leg_fill, leg_qty)
                if want_protective and not leg_placed:
                    _rollback(all_placed)
                    return {"status": "FAILED", "error": "partial protective placement failed", "order_ids": all_placed}
                all_placed.extend(leg_placed)
            return {"status": "SUCCESS" if all_placed else "skipped", "order_ids": all_placed}

        if signal.legs and len(signal.legs) == 1:
            leg = signal.legs[0]
            try:
                option_info = parse_option_symbol(leg.symbol)
            except Exception as e:  # noqa: BLE001
                return {"status": "FAILED", "error": f"parse leg failed: {e}", "order_ids": []}
            futu_code = _build_futu_option_code(
                option_info["symbol"],
                option_info["expiry_contract"],
                option_info["strike"],
                option_info["right"],
            )
            leg_is_long = leg.action.upper() == "BUY"
            leg_qty = leg.quantity or combo_qty
            placed = _place_leg_protective(futu_code, leg_is_long, fill_price, leg_qty)
            return {"status": "SUCCESS" if placed else "skipped", "order_ids": placed}

        return {"status": "skipped", "error": "no symbol or legs"}

    def _native_combo_available(self) -> bool:
        return (
            ComboLeg is not None
            and self.trd_ctx is not None
            and callable(getattr(self.trd_ctx, "place_combo_order", None))
        )

    def _leg_futu_code(self, leg: OptionLeg, meta: Dict[str, Any]) -> str:
        option_info = parse_option_symbol(
            leg.symbol,
            metadata=meta,
            strike=leg.strike,
            right=leg.option_type,
        )
        return _build_futu_option_code(
            option_info["symbol"],
            option_info["expiry_contract"],
            option_info["strike"],
            option_info["right"],
        )

    def _place_combo_order(self, signal: Signal, order_type_str: str, quantity: int) -> Dict[str, Any]:
        """
        原生组合下单（place_combo_order）。

        文档：https://openapi.futunn.com/futu-api-doc/trade/place-combo-order.html
        需要 futu-api>=10 与匹配版本的 OpenD；旧 SDK 明确报错，避免危险拆腿。
        """
        if not self._native_combo_available():
            return {
                "order_id": None,
                "status": "FAILED",
                "error": (
                    "当前 futu-api/OpenD 不支持 place_combo_order。"
                    "请升级 futu-api>=10.0 并使用匹配的 OpenD 后再下 PCS/垂直价差。"
                ),
            }

        # 富途模拟盘明确不支持组合期权；提前提示，避免落到「未知股票」等误导信息
        trd_env_name = str(getattr(self.trd_env, "name", self.trd_env) or "").upper()
        if trd_env_name == "SIMULATE" or self.trd_env == getattr(TrdEnv, "SIMULATE", "SIMULATE"):
            return {
                "order_id": None,
                "status": "FAILED",
                "error": (
                    "富途模拟交易不支持组合期权（place_combo_order）。"
                    "请改用富途真实账户下 PCS/垂直价差，或在模拟环境用 IBKR 验证链路。"
                ),
            }

        meta = signal.metadata or {}
        combo_legs = []
        for leg in signal.legs:
            cl = ComboLeg()
            cl.code = self._leg_futu_code(leg, meta)
            cl.trd_side = TrdSide.BUY if (leg.action or "").upper() == "BUY" else TrdSide.SELL
            # 实际腿数量 = qty × qty_ratio；等权垂直价差各腿 ratio=1
            leg_qty = max(1, int(leg.quantity or 1))
            cl.qty_ratio = float(leg_qty)
            combo_legs.append(cl)

        if order_type_str == "LMT" and signal.limit_price is not None:
            futu_order_type = OrderType.NORMAL
            price = abs(float(signal.limit_price))
        else:
            futu_order_type = OrderType.MARKET
            price = 0.0

        kwargs: Dict[str, Any] = {
            "combo_leg_list": combo_legs,
            "price": price,
            "qty": float(quantity),
            "order_type": futu_order_type,
            "trd_env": self.trd_env,
        }
        if TimeInForce is not None:
            kwargs["time_in_force"] = TimeInForce.DAY

        logger.info(
            "富途组合下单 place_combo_order: legs=%s qty=%s type=%s price=%s",
            [(c.code, str(c.trd_side), c.qty_ratio) for c in combo_legs],
            quantity,
            futu_order_type,
            price,
        )
        ret, data = self.trd_ctx.place_combo_order(**kwargs)
        if ret != RET_OK:
            raw = str(data)
            if "模拟交易不支持组合" in raw or "模拟" in raw and "组合" in raw:
                error_msg = (
                    "富途组合下单失败: 模拟交易不支持组合期权。"
                    "请改用富途真实账户，或在模拟环境用 IBKR 验证。"
                )
            elif "未知的协议" in raw or "unknown protocol" in raw.lower():
                ver = format_opend_server_ver(self.opend_server_ver)
                error_msg = (
                    f"富途组合下单失败: OpenD 协议不支持 place_combo_order"
                    f"（当前 OpenD {ver}，需 ≥{format_opend_server_ver(FUTU_MIN_COMBO_SERVER_VER)}）。"
                    "请升级并重启 Futu OpenD 后再试。"
                )
            elif "未知股票" in raw or "unknown stock" in raw.lower():
                codes = ", ".join(c.code for c in combo_legs)
                error_msg = (
                    f"富途组合下单失败: {raw}"
                    f"（提交代码: {codes}）。"
                    "若代码形如 US..SPXW… 属旧格式；指数期权应为 US.SPXW…。"
                    "并确认已开通美国市场期权交易/行情权限。"
                )
            else:
                warn = self.opend_version_warning
                error_msg = f"富途组合下单失败: {raw}"
                if warn and warn not in error_msg:
                    error_msg = f"{error_msg}；{warn}"
            logger.error(error_msg)
            return {"order_id": None, "status": "FAILED", "error": error_msg}

        order_id = ""
        if data is not None and len(data) > 0:
            order_id = str(data.iloc[0].get("order_id", "") or "")
        logger.info("富途组合下单成功: order_id=%s", order_id)
        return {"order_id": order_id, "status": "SUCCESS", "error": None}

    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        try:
            # 支持组合订单（逗号分隔的多个 order_id）
            ids = order_id.split(",")
            all_ok = True
            for oid in ids:
                oid = oid.strip()
                if not oid:
                    continue
                ret, data = self.trd_ctx.modify_order(
                    modify_order_op=ModifyOrderOp.CANCEL,
                    order_id=oid,
                    qty=0,
                    price=0,
                    trd_env=self.trd_env,
                )
                if ret != RET_OK:
                    logger.error(f"撤销订单失败 {oid}: {data}")
                    all_ok = False
                else:
                    logger.info(f"撤销订单成功: {oid}")
            return all_ok
        except Exception as e:
            logger.error(f"撤销订单失败: {e}")
            return False

    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """查询单个订单"""
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        try:
            # 对于组合订单，查询第一个子订单
            first_id = order_id.split(",")[0].strip()

            ret, data = self.trd_ctx.order_list_query(
                order_id=first_id,
                trd_env=self.trd_env,
            )
            if ret != RET_OK or data is None or len(data) == 0:
                return None

            row = data.iloc[0]
            return self._format_order_row(row)

        except Exception as e:
            logger.warning(f"查询订单失败 {order_id}: {e}")
            return None

    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询订单列表"""
        if not self.connected or not self.trd_ctx:
            raise RuntimeError("未连接到富途")

        try:
            ret, data = self.trd_ctx.order_list_query(trd_env=self.trd_env)
            if ret != RET_OK or data is None:
                return []

            result = []
            for _, row in data.iterrows():
                order_info = self._format_order_row(row)
                if status and order_info.get("status") != status:
                    continue
                result.append(order_info)

            return result
        except Exception as e:
            logger.error(f"查询订单列表失败: {e}")
            return []

    def _format_order_row(self, row) -> Dict[str, Any]:
        """格式化单条订单数据"""
        order_status_raw = str(row.get("order_status", "NONE"))
        std_status = FUTU_STATUS_MAP.get(order_status_raw, StandardOrderStatus.UNKNOWN)
        status_cn = FUTU_STATUS_CN.get(order_status_raw, order_status_raw)

        sf = self._safe_float
        filled = int(sf(row.get("dealt_qty")))
        quantity = int(sf(row.get("qty")))
        avg_price = sf(row.get("dealt_avg_price"))

        return {
            "order_id": str(row.get("order_id", "")),
            "status": status_cn,
            "std_status": std_status.value,
            "raw_status": order_status_raw,
            "order_type": "市价" if str(row.get("order_type", "")) == "MARKET" else "限价",
            "order_type_raw": str(row.get("order_type", "")),
            "quantity": quantity,
            "filled": filled,
            "remaining": quantity - filled,
            "avg_fill_price": avg_price if avg_price > 0 else None,
            "limit_price": sf(row.get("price")) or None,
            "commission": None,
        }

    def supports_combined_order(self) -> bool:
        """富途 OpenAPI 支持组合期权/策略单（place_combo_order，futu-api>=10）。"""
        return True
