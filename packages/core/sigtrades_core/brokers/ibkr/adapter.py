#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IBKR (Interactive Brokers) 适配器实现
使用 ib_async 库与 TWS 交互

IBKR Broker Adapter Implementation
Uses ib_async library to interact with TWS
"""

import logging
import re
from typing import List, Dict, Any, Optional
from datetime import datetime

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_core.signal.models import Signal, OptionLeg
from sigtrades_core.signal.option_symbol import parse_option_symbol
from sigtrades_core.trading.order_status import OrderStatus as StandardOrderStatus


logger = logging.getLogger(__name__)

# 延迟导入标志
_ib_async_imported = False
_ib_async_import_error: Optional[str] = None
IB = None
Option = None
Bag = None
ComboLeg = None
LimitOrder = None
MarketOrder = None
util = None


def _ensure_ib_async_imported():
    """确保 ib_async 已导入（延迟导入，避免模块级别事件循环问题）"""
    global _ib_async_imported, _ib_async_import_error
    global IB, Option, Bag, ComboLeg, LimitOrder, MarketOrder, util
    
    if _ib_async_imported:
        return True
    
    try:
        # 确保有事件循环
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # 导入 ib_async
        from ib_async import IB as _IB, Option as _Option, Bag as _Bag
        from ib_async import ComboLeg as _ComboLeg, LimitOrder as _LimitOrder, MarketOrder as _MarketOrder
        from ib_async import util as _util
        
        IB = _IB
        Option = _Option
        Bag = _Bag
        ComboLeg = _ComboLeg
        LimitOrder = _LimitOrder
        MarketOrder = _MarketOrder
        util = _util
        
        _ib_async_imported = True
        _ib_async_import_error = None
        logger.info("ib_async 模块导入成功")
        return True
        
    except ImportError as e:
        _ib_async_import_error = str(e)
        logger.warning(f"无法导入 ib_async 模块: {e}，IBKR 功能不可用")
        return False
    except Exception as e:
        _ib_async_import_error = str(e)
        logger.error(f"导入 ib_async 失败: {e}")
        return False


# IBKR 订单状态映射
IBKR_STATUS_MAP = {
    'Submitted': StandardOrderStatus.SUBMITTED,
    'Filled': StandardOrderStatus.FILLED,
    'PartiallyFilled': StandardOrderStatus.PARTIALLY_FILLED,
    'Cancelled': StandardOrderStatus.CANCELLED,
    'Inactive': StandardOrderStatus.REJECTED,
    'PendingSubmit': StandardOrderStatus.PENDING,
    'PreSubmitted': StandardOrderStatus.PENDING,
    'PendingCancel': StandardOrderStatus.PENDING,
    'ApiCancelled': StandardOrderStatus.CANCELLED,
    'ApiPending': StandardOrderStatus.PENDING,
}


class IBKRBrokerAdapter(BaseBrokerAdapter):
    """
    IBKR (Interactive Brokers) 适配器
    
    使用 ib_async 库连接 TWS
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化 IBKR 适配器
        
        Args:
            config: 券商配置，包含：
                - host: TWS 地址，默认 127.0.0.1
                - port: 端口号
                    - 7497: TWS 模拟盘
                    - 7496: TWS 实盘
                - client_id: 客户端ID，默认 1
                - account: 账户ID（可选，多账户时指定）
                - timeout: 连接超时秒数，默认 10
                - readonly: 只读模式，默认 False
        """
        super().__init__(config)
        
        # 延迟导入 ib_async（失败时带上底层原因，便于打包缺依赖时排查）
        if not _ensure_ib_async_imported():
            detail = _ib_async_import_error or "unknown"
            raise RuntimeError(
                f"ib_async 导入失败: {detail}。"
                "常见于 Agent 打包缺少 numpy/eventkit，请重新安装 Agent；"
                "开发环境可执行: pip install ib_async numpy"
            )
        
        self.host = config.get("host", "127.0.0.1")
        self.port = config.get("port", 7497)
        self.client_id = config.get("client_id", 1)
        self.account = config.get("account", "")
        self.timeout = config.get("timeout", 10)
        self.readonly = config.get("readonly", False)
        
        # IB 连接实例
        self.ib: Optional[IB] = None
        
        # 缓存合约信息（避免重复查询 conId）
        self._contract_cache: Dict[str, Any] = {}
    
    def connect(self) -> bool:
        """连接到 TWS"""
        try:
            if not IB:
                logger.error("ib_async 模块未安装")
                self.connected = False
                return False
            
            # 创建 IB 实例
            self.ib = IB()
            # ib_async 默认 RequestTimeout=0（永不超时）；账户摘要请求卡住时会堵死执行器线程
            self.ib.RequestTimeout = float(self.timeout or 10)
            
            # 连接
            logger.info(f"正在连接 IBKR: {self.host}:{self.port}, clientId={self.client_id}")
            self.ib.connect(
                host=self.host,
                port=self.port,
                clientId=self.client_id,
                timeout=self.timeout,
                readonly=self.readonly
            )
            
            if not self.ib.isConnected():
                logger.error("IBKR 连接失败")
                self.connected = False
                return False
            
            # 获取账户列表
            accounts = self.ib.managedAccounts()
            if accounts:
                if not self.account:
                    self.account = accounts[0]
                logger.info(f"IBKR 连接成功，账户: {self.account}, 可用账户: {accounts}")
            else:
                logger.warning("IBKR 连接成功，但未获取到账户信息")
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"连接 IBKR 失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            self.connected = False
            return False
    
    def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self.ib and self.ib.isConnected():
                self.ib.disconnect()
            self.connected = False
            self.ib = None
            self._contract_cache.clear()
            logger.info("已断开 IBKR 连接")
            return True
        except Exception as e:
            logger.error(f"断开 IBKR 连接失败: {e}")
            return False
    
    def is_connected(self) -> bool:
        """检查是否已连接（覆盖基类方法，实际检查 IBKR 连接状态）"""
        if not self.connected or not self.ib:
            return False
        try:
            return self.ib.isConnected()
        except Exception:
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息。

        优先用非阻塞的 accountValues（connect 后通常已有缓存）。
        accountSummary 首次会同步请求且在 API 卡住时可能堵死执行器，仅作受限回退。
        """
        if not self.connected or not self.ib:
            raise RuntimeError("未连接到 IBKR")

        try:
            accounts = list(self.ib.managedAccounts() or [])
            if accounts and (not self.account or self.account not in accounts):
                self.account = accounts[0]
                logger.info("IBKR 使用托管账户: %s (可用: %s)", self.account, accounts)

            account_values = list(self.ib.accountValues(self.account or "") or [])
            if not account_values:
                account_values = list(self.ib.accountValues() or [])

            if not account_values:
                # 缓存尚未就绪：有超时的 accountSummary 回退（避免 RequestTimeout=0 永久阻塞）
                prev_timeout = getattr(self.ib, "RequestTimeout", 0)
                self.ib.RequestTimeout = float(self.timeout or 10)
                try:
                    for attempt in range(3):
                        account_values = list(self.ib.accountSummary(self.account or "") or [])
                        if not account_values and self.account:
                            account_values = list(self.ib.accountSummary() or [])
                        if account_values:
                            break
                        if attempt < 2:
                            self.ib.sleep(0.5)
                except Exception as e:  # noqa: BLE001
                    raise RuntimeError(
                        f"IBKR 账户摘要超时/失败（{type(e).__name__}），"
                        "请重启 TWS 或在 Agent 点重连后再测"
                    ) from e
                finally:
                    self.ib.RequestTimeout = prev_timeout

            info = {
                "account": self.account,
                "account_id": self.account,
                "is_paper": self.port == 7497,  # TWS 模拟盘端口
                "currency": "USD",
                "net_liquidation": None,
                "total_assets": None,
                "available_cash": None,
                "positions_value": None,
                "equity": None,
                "margin_used": None,
                "unrealized_pl": None,
                "realized_pl": None,
            }

            # tag -> (currency -> value)；优先 USD，其次 BASE，再任意
            by_tag: Dict[str, Dict[str, float]] = {}
            for av in account_values:
                if self.account and getattr(av, "account", "") and av.account != self.account:
                    continue
                tag = getattr(av, "tag", None) or ""
                cur = (getattr(av, "currency", None) or "").upper() or "BASE"
                try:
                    value_float = float(av.value) if av.value not in (None, "") else None
                except (ValueError, TypeError):
                    value_float = None
                if value_float is None:
                    continue
                by_tag.setdefault(tag, {})[cur] = value_float

            def _pick(tag: str) -> Optional[float]:
                cur_map = by_tag.get(tag) or {}
                for key in ("USD", "BASE"):
                    if key in cur_map:
                        return cur_map[key]
                if cur_map:
                    return next(iter(cur_map.values()))
                return None

            net = _pick("NetLiquidation")
            cash = _pick("AvailableFunds")
            if cash is None:
                cash = _pick("TotalCashValue")
            info["net_liquidation"] = net
            info["total_assets"] = net
            info["available_cash"] = cash
            info["positions_value"] = _pick("GrossPositionValue")
            info["equity"] = _pick("EquityWithLoanValue")
            info["margin_used"] = _pick("InitMarginReq")
            info["unrealized_pl"] = _pick("UnrealizedPnL")
            info["realized_pl"] = _pick("RealizedPnL")

            if net is None and cash is None:
                raise RuntimeError(
                    f"IBKR 已连接但账户摘要为空 account={self.account!r} "
                    f"managed={accounts} summary_rows={len(account_values)}"
                )

            return info

        except Exception as e:
            logger.error(f"获取 IBKR 账户信息失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def get_option_positions(self) -> List[Dict[str, Any]]:
        """获取期权持仓列表"""
        if not self.connected or not self.ib:
            raise RuntimeError("未连接到 IBKR")
        
        try:
            positions = self.ib.positions(self.account)
            
            result = []
            for pos in positions:
                contract = pos.contract
                
                # 只处理期权
                if contract.secType != 'OPT':
                    continue
                
                quantity = int(pos.position)
                if quantity == 0:
                    continue
                
                avg_cost = float(pos.avgCost) if pos.avgCost else 0.0
                
                # 构建期权标识符
                symbol = f"{contract.symbol}  {contract.lastTradeDateOrContractMonth}{contract.right}{int(contract.strike * 1000):08d}"
                
                result.append({
                    "symbol": symbol,
                    "type": "Call" if contract.right == 'C' else "Put",
                    "direction": "买入" if quantity > 0 else "卖出",
                    "quantity": abs(quantity),
                    "cost": f"${avg_cost:.2f}",
                    "strike": contract.strike,
                    "put_call": 'CALL' if contract.right == 'C' else 'PUT',
                    "base_symbol": contract.symbol,
                    "expiry": contract.lastTradeDateOrContractMonth,
                    "raw_quantity": quantity,
                    "con_id": contract.conId
                })
            
            logger.info(f"获取到 {len(result)} 条期权持仓")
            return result
            
        except Exception as e:
            logger.error(f"获取 IBKR 期权持仓失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            raise
    
    def _ensure_event_loop(self):
        """确保当前线程有事件循环"""
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    
    def _create_option_contract(self, symbol: str, expiry: str, strike: float, right: str) -> Any:
        """
        创建并验证期权合约
        
        Args:
            symbol: 标的代码，如 'SPX', 'SPXW'
            expiry: 到期日，格式 'YYYYMMDD'
            strike: 行权价
            right: 'C' (Call) 或 'P' (Put)
        
        Returns:
            验证后的 Option 合约对象（包含 conId）
        """
        logger.info(f"[_create_option_contract] 创建合约: {symbol} {expiry} {strike} {right}")
        
        # 检查缓存
        cache_key = f"{symbol}_{expiry}_{strike}_{right}"
        if cache_key in self._contract_cache:
            cached = self._contract_cache[cache_key]
            # 确保缓存的合约有效（conId != 0）
            if cached and cached.conId != 0:
                logger.info(f"[_create_option_contract] 使用缓存合约: {cache_key}, conId={cached.conId}")
                return cached
            else:
                # 清除无效缓存
                logger.warning(f"[_create_option_contract] 清除无效缓存: {cache_key}")
                del self._contract_cache[cache_key]
        
        # 创建合约
        logger.info(f"[_create_option_contract] 创建 Option 对象...")
        
        # IBKR 使用 SPX 作为所有 SPX 期权（包括周期权 SPXW）的 symbol
        ibkr_symbol = symbol
        if symbol == 'SPXW':
            ibkr_symbol = 'SPX'
            logger.info(f"[_create_option_contract] 将 SPXW 转换为 SPX (IBKR 格式)")
        
        # SPX 期权需要指定 CBOE 交易所
        if ibkr_symbol in ('SPX',):
            exchange = 'CBOE'
        else:
            exchange = 'SMART'
        
        contract = Option(
            symbol=ibkr_symbol,
            lastTradeDateOrContractMonth=expiry,
            strike=strike,
            right=right,
            exchange=exchange,
            currency='USD'
        )
        logger.info(f"[_create_option_contract] IBKR symbol={ibkr_symbol}, 交易所={exchange}")
        
        # 验证合约获取 conId
        logger.info(f"[_create_option_contract] 调用 qualifyContracts 验证合约...")
        qualified = self.ib.qualifyContracts(contract)
        logger.info(f"[_create_option_contract] qualifyContracts 返回: {qualified}")
        
        # 检查验证结果
        if not qualified or qualified[0] is None or contract.conId == 0:
            error_msg = f"无法验证期权合约: {symbol} {expiry} {strike} {right} (可能已过期或不存在)"
            logger.error(f"[_create_option_contract] {error_msg}")
            raise ValueError(error_msg)
        
        # 缓存
        self._contract_cache[cache_key] = contract
        logger.info(f"[_create_option_contract] 合约创建成功: conId={contract.conId}")
        
        return contract
    
    def _create_combo_contract(self, signal: Signal) -> Any:
        """
        创建组合合约（Bag）
        
        Args:
            signal: 交易信号，包含多个腿
        
        Returns:
            Bag 合约对象
        """
        logger.info(f"[_create_combo_contract] 开始创建组合合约, 腿数量={len(signal.legs) if signal.legs else 0}")
        
        if not signal.legs or len(signal.legs) < 2:
            raise ValueError("组合订单至少需要2条腿")
        
        # 创建各腿合约
        leg_contracts = []
        meta = signal.metadata or {}
        for i, leg in enumerate(signal.legs):
            logger.info(f"[_create_combo_contract] 处理第 {i+1} 条腿: {leg.symbol}")
            option_info = parse_option_symbol(
                leg.symbol,
                metadata=meta,
                strike=leg.strike,
                right=leg.option_type,
            )
            logger.info(f"[_create_combo_contract] 解析结果: {option_info}")
            contract = self._create_option_contract(
                symbol=option_info['symbol'],
                expiry=option_info['expiry_contract'],
                strike=option_info['strike'],
                right=option_info['right']
            )
            leg_contracts.append((contract, leg))
            logger.info(f"[_create_combo_contract] 第 {i+1} 条腿合约创建完成")
        
        # 创建 Bag 合约
        logger.info("[_create_combo_contract] 创建 Bag 合约...")
        bag = Bag()
        bag.symbol = leg_contracts[0][0].symbol
        
        # SPX/SPXW 组合需要 CBOE 交易所
        first_symbol = leg_contracts[0][0].symbol
        if first_symbol in ('SPX', 'SPXW'):
            bag_exchange = 'CBOE'
        else:
            bag_exchange = 'SMART'
        
        bag.exchange = bag_exchange
        bag.currency = 'USD'
        bag.comboLegs = []
        logger.info(f"[_create_combo_contract] Bag 交易所: {bag_exchange}")
        
        for contract, leg in leg_contracts:
            combo_leg = ComboLeg()
            combo_leg.conId = contract.conId
            combo_leg.ratio = 1
            combo_leg.action = leg.action  # 'BUY' or 'SELL'
            combo_leg.exchange = bag_exchange
            bag.comboLegs.append(combo_leg)
        
        logger.info(f"[_create_combo_contract] 组合合约创建完成: {len(bag.comboLegs)} 条腿")
        return bag

    def _place_stock_order(self, signal: Signal) -> Dict[str, Any]:
        """股票现货下单。"""
        if not _ensure_ib_async_imported():
            return {"order_id": None, "status": "FAILED", "error": "ib_async unavailable"}
        from ib_async import Stock

        symbol = (signal.symbol or "").upper()
        action = (signal.action or "BUY").upper()
        quantity = signal.quantity or 1
        order_type = signal.order_type or "MKT"
        contract = Stock(symbol, "SMART", "USD")
        if order_type == "LMT" and signal.limit_price is not None:
            order = LimitOrder(action, quantity, float(signal.limit_price))
        else:
            order = MarketOrder(action, quantity)
        order.account = self.account
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(1.0)
        order_id = str(trade.order.orderId)
        return {"order_id": order_id, "status": "SUCCESS", "error": None}

    def place_protective_orders(
        self,
        signal: Signal,
        fill_price: float,
        *,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """止损/止盈子单（股票或单腿期权）。"""
        if not _ensure_ib_async_imported() or not self.ib:
            return {"status": "skipped", "error": "ib_async unavailable"}
        from ib_async import Stock, StopOrder, LimitOrder
        from sigtrades_core.brokers.stock_utils import is_stock_signal

        qty = signal.quantity or 1
        is_long = (signal.action or "BUY").upper() in ("BUY", "OPEN")
        exit_action = "SELL" if is_long else "BUY"
        placed = []

        if is_stock_signal(signal):
            symbol = (signal.symbol or "").upper()
            contract = Stock(symbol, "SMART", "USD")
        elif signal.legs and len(signal.legs) == 1:
            leg = signal.legs[0]
            is_long = leg.action.upper() == "BUY"
            exit_action = "SELL" if is_long else "BUY"
            qty = signal.quantity or 1
            option_info = parse_option_symbol(leg.symbol)
            contract = self._create_option_contract(
                symbol=option_info["symbol"],
                expiry=option_info["expiry_contract"],
                strike=option_info["strike"],
                right=option_info["right"],
            )
        elif signal.legs and len(signal.legs) > 1:
            contract = self._create_combo_contract(signal)
            qty = signal.quantity or 1
            is_long = (signal.action or "BUY").upper() in ("BUY", "OPEN")
            exit_action = "SELL" if is_long else "BUY"
            placed = []
            if stop_loss_pct is not None:
                stop_px = fill_price * (1 - stop_loss_pct / 100) if is_long else fill_price * (1 + stop_loss_pct / 100)
                stop = StopOrder(exit_action, qty, round(stop_px, 2))
                stop.account = self.account
                trade = self.ib.placeOrder(contract, stop)
                placed.append(str(trade.order.orderId))
            if take_profit_pct is not None:
                tp_px = fill_price * (1 + take_profit_pct / 100) if is_long else fill_price * (1 - take_profit_pct / 100)
                tp = LimitOrder(exit_action, qty, round(tp_px, 2))
                tp.account = self.account
                trade = self.ib.placeOrder(contract, tp)
                placed.append(str(trade.order.orderId))
            return {"status": "SUCCESS", "order_ids": placed}
        else:
            return {"status": "skipped", "error": "no legs for protective"}

        if stop_loss_pct is not None:
            stop_px = fill_price * (1 - stop_loss_pct / 100) if is_long else fill_price * (1 + stop_loss_pct / 100)
            stop = StopOrder(exit_action, qty, round(stop_px, 2))
            stop.account = self.account
            trade = self.ib.placeOrder(contract, stop)
            placed.append(str(trade.order.orderId))
        if take_profit_pct is not None:
            tp_px = fill_price * (1 + take_profit_pct / 100) if is_long else fill_price * (1 - take_profit_pct / 100)
            tp = LimitOrder(exit_action, qty, round(tp_px, 2))
            tp.account = self.account
            trade = self.ib.placeOrder(contract, tp)
            placed.append(str(trade.order.orderId))
        return {"status": "SUCCESS", "order_ids": placed}
    
    def place_order(self, signal: Signal) -> Dict[str, Any]:
        """
        提交订单（单个期权或组合订单）
        
        Args:
            signal: 交易信号
            
        Returns:
            {
                "order_id": "订单ID",
                "status": "SUCCESS" 或 "FAILED",
                "error": "错误信息（如果有）",
                "perm_id": "永久订单ID"
            }
        """
        logger.info(f"[place_order] 开始处理订单: signal_id={signal.signal_id}")

        from sigtrades_core.brokers.stock_utils import is_stock_signal
        if is_stock_signal(signal):
            return self._place_stock_order(signal)
        
        if not self.connected or not self.ib:
            logger.error("[place_order] 未连接到 IBKR")
            raise RuntimeError("未连接到 IBKR")
        
        # 检查实际连接状态
        if not self.ib.isConnected():
            logger.error("[place_order] IBKR 连接已断开")
            raise RuntimeError("IBKR 连接已断开")
        
        logger.info("[place_order] 连接状态检查通过")
        
        try:
            # 确定订单类型
            order_type = signal.order_type if signal.order_type else "MKT"
            quantity = signal.quantity or 1
            logger.info(f"[place_order] 订单类型={order_type}, 数量={quantity}")
            
            if quantity <= 0:
                raise ValueError(f"订单数量无效: {quantity}")
            
            # 创建合约
            logger.info(f"[place_order] 开始创建合约, legs数量={len(signal.legs) if signal.legs else 0}")
            if signal.legs and len(signal.legs) > 1:
                # 组合订单
                contract = self._create_combo_contract(signal)
                logger.info(f"提交组合订单: {len(signal.legs)} 条腿, 数量={quantity}")
            else:
                # 单腿订单
                if signal.legs and len(signal.legs) == 1:
                    leg = signal.legs[0]
                    option_info = parse_option_symbol(
                        leg.symbol,
                        metadata=signal.metadata or {},
                        strike=leg.strike,
                        right=leg.option_type,
                    )
                else:
                    raise ValueError("单腿订单必须包含腿信息")
                
                contract = self._create_option_contract(
                    symbol=option_info['symbol'],
                    expiry=option_info['expiry_contract'],
                    strike=option_info['strike'],
                    right=option_info['right']
                )
                logger.info(f"提交单腿订单: {leg.symbol}, 数量={quantity}")
            
            # 创建订单
            logger.info(f"[place_order] 合约创建完成，开始创建订单对象")
            if order_type == "LMT" and signal.limit_price is not None:
                # 限价单
                # IBKR 组合订单的限价是净价格（正数=净信用，负数=净借记）
                limit_price = abs(signal.limit_price)
                order = LimitOrder('BUY', quantity, limit_price)
                logger.info(f"[place_order] 创建限价单: 价格=${limit_price:.2f}")
            else:
                # 市价单
                order = MarketOrder('BUY', quantity)
                logger.info("[place_order] 创建市价单")
            
            # 设置账户
            order.account = self.account
            logger.info(f"[place_order] 订单账户设置完成: {self.account}")
            
            # 提交订单
            logger.info("[place_order] 准备调用 ib.placeOrder...")
            trade = self.ib.placeOrder(contract, order)
            logger.info(f"[place_order] placeOrder 返回: orderId={trade.order.orderId}")
            
            # 等待订单确认 - 使用较长等待时间，因为 IBKR 可能有 TIF 警告延迟
            logger.info("[place_order] 等待订单确认 (1秒)...")
            self.ib.sleep(1.0)
            logger.info("[place_order] 等待完成")
            
            order_id = str(trade.order.orderId)
            perm_id = str(trade.order.permId) if trade.order.permId else ""
            order_status = trade.orderStatus.status
            
            # 关键修复：检查是否有成交记录
            # IBKR 的 TIF 警告会导致状态显示 Cancelled，但订单实际上可能已成交
            if trade.fills:
                total_filled = sum(f.execution.shares for f in trade.fills)
                if total_filled > 0:
                    order_status = "Filled" if total_filled >= order.totalQuantity else "PartiallyFilled"
                    logger.info(f"订单有成交记录: filled={total_filled}, 修正状态为 {order_status}")
            
            logger.info(f"订单提交成功: order_id={order_id}, perm_id={perm_id}, status={order_status}")
            
            return {
                "order_id": order_id,
                "status": "SUCCESS",
                "perm_id": perm_id,
                "order_status": order_status
            }
            
        except Exception as e:
            logger.error(f"IBKR 下单失败: {e}")
            import traceback
            logger.error(f"错误详情: {traceback.format_exc()}")
            return {
                "order_id": "",
                "status": "FAILED",
                "error": str(e)
            }
    
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        if not self.connected or not self.ib:
            raise RuntimeError("未连接到 IBKR")
        
        self._ensure_event_loop()
        
        try:
            # 查找订单
            trades = self.ib.trades()
            for trade in trades:
                if str(trade.order.orderId) == order_id:
                    self.ib.cancelOrder(trade.order)
                    self.ib.sleep(0.3)
                    logger.info(f"订单撤销请求已发送: {order_id}")
                    return True
            
            logger.warning(f"未找到订单: {order_id}")
            return False
            
        except Exception as e:
            logger.error(f"撤销订单失败: {e}")
            return False
    
    def get_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        """
        查询单个订单
        
        Args:
            order_id: 订单ID
        
        Returns:
            订单信息字典，如果未找到返回 None
        """
        if not self.connected or not self.ib:
            raise RuntimeError("未连接到 IBKR")
        
        self._ensure_event_loop()
        
        try:
            # 关键：先让 ib_async 处理挂起的事件，确保状态是最新的
            # 使用 1 秒等待，因为 IBKR 的状态更新可能有延迟
            self.ib.sleep(1.0)
            
            # 先检查 fills，因为已成交的订单信息更准确
            fills = self.ib.fills()
            order_fills = [f for f in fills if str(f.execution.orderId) == order_id]
            if order_fills:
                # 有成交记录，计算总成交量
                total_filled = sum(f.execution.shares for f in order_fills)
                total_commission = sum(
                    f.commissionReport.commission 
                    for f in order_fills 
                    if f.commissionReport and f.commissionReport.commission
                )
                # 计算加权平均成交价
                total_amount = sum(f.execution.shares * f.execution.price for f in order_fills)
                avg_price = total_amount / total_filled if total_filled > 0 else 0
                
                logger.info(f"订单 {order_id} 有成交记录: filled={total_filled}, avg_price={avg_price}")
                
                # 同时检查 trades 获取完整订单信息
                trades = self.ib.trades()
                for trade in trades:
                    if str(trade.order.orderId) == order_id:
                        # 用 fills 的数据覆盖 trade 的状态
                        order_info = self._format_order(trade)
                        order_info['filled'] = int(total_filled)
                        order_info['avg_fill_price'] = avg_price
                        order_info['commission'] = total_commission
                        # 根据成交情况判断状态
                        quantity = int(trade.order.totalQuantity) if trade.order.totalQuantity else 0
                        if total_filled >= quantity:
                            order_info['status'] = 'Filled'
                            order_info['status_cn'] = '已成交'
                            order_info['std_status'] = StandardOrderStatus.FILLED.value
                        elif total_filled > 0:
                            order_info['status'] = 'PartiallyFilled'
                            order_info['status_cn'] = '部分成交'
                            order_info['std_status'] = StandardOrderStatus.PARTIALLY_FILLED.value
                        return order_info
                
                # 如果 trades 中没找到，直接返回 fill 信息
                return {
                    "order_id": order_id,
                    "status": "Filled",
                    "status_cn": "已成交",
                    "std_status": StandardOrderStatus.FILLED.value,
                    "filled": int(total_filled),
                    "remaining": 0,
                    "avg_fill_price": avg_price,
                    "commission": total_commission,
                }
            
            # 没有成交记录，从活动订单中查找
            trades = self.ib.trades()
            for trade in trades:
                if str(trade.order.orderId) == order_id:
                    return self._format_order(trade)
            
            logger.debug(f"未找到订单: {order_id}")
            return None
            
        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            return None
    
    def _format_order(self, trade) -> Dict[str, Any]:
        """格式化订单信息"""
        order = trade.order
        status = trade.orderStatus
        
        # 计算佣金，并从 fills 汇总成交（orderStatus.filled 偶发为 0 却已有成交）
        commission = 0.0
        fills_qty = 0.0
        fills_notional = 0.0
        for fill in trade.fills or []:
            if fill.commissionReport and fill.commissionReport.commission:
                commission += fill.commissionReport.commission
            shares = float(getattr(fill.execution, "shares", 0) or 0)
            price = float(getattr(fill.execution, "avgPrice", 0) or 0)
            fills_qty += shares
            fills_notional += shares * price
        
        # 获取成交数量：优先 orderStatus，否则回退 trade.fills
        filled = int(status.filled) if status.filled else 0
        if filled <= 0 and fills_qty > 0:
            filled = int(fills_qty)
        remaining = int(status.remaining) if status.remaining else 0
        quantity = int(order.totalQuantity) if order.totalQuantity else 0
        if remaining <= 0 and quantity > 0 and filled < quantity:
            remaining = quantity - filled
        elif filled > 0 and remaining < 0:
            remaining = max(0, quantity - filled)
        
        avg_fill = float(status.avgFillPrice) if status.avgFillPrice else None
        if (avg_fill is None or avg_fill <= 0) and fills_qty > 0:
            avg_fill = fills_notional / fills_qty

        # 映射状态：有成交时绝不能信 TIF 等误报的 Cancelled
        ibkr_status = status.status
        if filled > 0 and (remaining == 0 or (quantity > 0 and filled >= quantity)):
            effective_status = 'Filled'
            std_status = StandardOrderStatus.FILLED
            remaining = 0
            logger.debug(
                "订单 %s 根据成交判定为已成交: filled=%s status_raw=%s",
                order.orderId, filled, ibkr_status,
            )
        elif filled > 0:
            effective_status = 'PartiallyFilled'
            std_status = StandardOrderStatus.PARTIALLY_FILLED
        else:
            effective_status = ibkr_status
            std_status = IBKR_STATUS_MAP.get(ibkr_status, StandardOrderStatus.UNKNOWN)
        
        return {
            "order_id": str(order.orderId),
            "perm_id": str(order.permId) if order.permId else "",
            "status": effective_status,
            "status_cn": self._get_status_cn(effective_status),
            "std_status": std_status.value,
            "filled": filled,
            "remaining": remaining,
            "avg_fill_price": avg_fill,
            "commission": commission,
            "order_type": order.orderType,
            "order_type_raw": order.orderType,
            "limit_price": float(order.lmtPrice) if order.lmtPrice else None,
            "quantity": quantity,
            "action": order.action,
            "filled_cash_amount": None  # IBKR 不直接提供此字段
        }
    
    def _format_fill(self, fill) -> Dict[str, Any]:
        """格式化成交信息"""
        execution = fill.execution
        commission = fill.commissionReport.commission if fill.commissionReport else 0.0
        
        return {
            "order_id": str(execution.orderId),
            "perm_id": str(execution.permId) if execution.permId else "",
            "status": "Filled",
            "status_cn": "已成交",
            "std_status": StandardOrderStatus.FILLED.value,
            "filled": int(execution.shares) if execution.shares else 0,
            "remaining": 0,
            "avg_fill_price": float(execution.avgPrice) if execution.avgPrice else None,
            "commission": commission,
            "order_type": None,
            "order_type_raw": None,
            "limit_price": None,
            "quantity": int(execution.shares) if execution.shares else 0,
            "action": execution.side,
            "filled_cash_amount": None
        }
    
    def _get_status_cn(self, status: str) -> str:
        """获取状态中文名"""
        status_cn_map = {
            'Submitted': '已提交',
            'Filled': '已成交',
            'PartiallyFilled': '部分成交',
            'Cancelled': '已取消',
            'Inactive': '无效',
            'PendingSubmit': '待提交',
            'PreSubmitted': '预提交',
            'PendingCancel': '待取消',
            'ApiCancelled': '已取消',
            'ApiPending': '待处理',
        }
        return status_cn_map.get(status, status)
    
    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        查询订单列表
        
        Args:
            status: 订单状态筛选（可选）
        
        Returns:
            订单列表
        """
        if not self.connected or not self.ib:
            raise RuntimeError("未连接到 IBKR")
        
        self._ensure_event_loop()
        
        try:
            result = []
            
            # 获取活动订单
            trades = self.ib.trades()
            for trade in trades:
                order_info = self._format_order(trade)
                
                # 状态筛选
                if status and order_info['status'] != status:
                    continue
                
                result.append(order_info)
            
            logger.info(f"获取到 {len(result)} 条订单")
            return result
            
        except Exception as e:
            logger.error(f"查询订单列表失败: {e}")
            return []
    
    def supports_combined_order(self) -> bool:
        """是否支持组合下单"""
        return True
