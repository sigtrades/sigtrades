#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
信号数据模型
Signal Data Models
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class SignalStatus(Enum):
    """信号状态"""
    PENDING = "pending"  # 待验证
    VALIDATED = "validated"  # 验证通过
    VALIDATION_FAILED = "validation_failed"  # 验证失败
    EXECUTED = "executed"  # 已执行
    REJECTED = "rejected"  # 已拒绝
    EXECUTION_FAILED = "execution_failed"  # 执行失败


class SignalCategory(str, Enum):
    """信号类别"""
    TRADE = "TRADE"  # 交易信号
    SMART_MONEY = "SMART_MONEY"  # 聪明钱信号
    UNUSUAL_ACTIVITY = "UNUSUAL_ACTIVITY"  # 异常活动
    ALERT = "ALERT"  # 市场提示


class AssetClass(str, Enum):
    """资产类型"""
    SPX_OPTIONS = "SPX_OPTIONS"  # SPX期权
    STOCK_OPTIONS = "STOCK_OPTIONS"  # 个股期权
    STOCK = "STOCK"  # 股票现货
    CRYPTO = "CRYPTO"  # 加密货币（BTC/ETH等）
    PREDICTION = "PREDICTION"  # 预测市场（Polymarket等）


class SignalSubtype(str, Enum):
    """信号子类型"""
    # TRADE 子类型
    OPEN = "OPEN"  # 建仓
    CLOSE = "CLOSE"  # 平仓
    ADJUST = "ADJUST"  # 调仓
    # SMART_MONEY 子类型
    WHALE_BUY = "WHALE_BUY"  # 大户买入
    WHALE_SELL = "WHALE_SELL"  # 大户卖出
    INSIDER = "INSIDER"  # 内幕交易迹象
    DARK_POOL = "DARK_POOL"  # 暗池大单
    # UNUSUAL_ACTIVITY 子类型
    HIGH_VOLUME = "HIGH_VOLUME"  # 异常成交量
    IV_SPIKE = "IV_SPIKE"  # IV飙升
    OI_CHANGE = "OI_CHANGE"  # 持仓量异常变化
    SWEEP = "SWEEP"  # 扫单
    HIGH_PRIORITY = "HIGH_PRIORITY"  # 高优先级（兼容旧代码）
    MEDIUM_PRIORITY = "MEDIUM_PRIORITY"  # 中优先级
    LOW_PRIORITY = "LOW_PRIORITY"  # 低优先级
    # ALERT 子类型
    MARKET_OPEN = "MARKET_OPEN"  # 市场开盘
    MARKET_CLOSE = "MARKET_CLOSE"  # 市场收盘
    EXPIRY_REMINDER = "EXPIRY_REMINDER"  # 到期提醒
    RISK_ALERT = "RISK_ALERT"  # 风险提示
    POSITION_ALERT = "POSITION_ALERT"  # 持仓提醒


@dataclass
class OptionLeg:
    """期权组合订单的单个腿"""
    symbol: str  # 期权代码
    action: str  # BUY/SELL
    quantity: int  # 数量
    limit_price: Optional[float] = None  # 限价
    strike: Optional[float] = None  # 行权价
    option_type: Optional[str] = None  # 期权类型：CALL/PUT


@dataclass
class ExecutionConfig:
    """订单执行配置（由后端下发）"""
    max_retry_attempts: int = 5  # 最大重试次数，默认5
    limit_order_attempts: int = 1  # 限价单尝试次数，默认1（第一次限价，后面市价）
    order_wait_timeout: int = 60  # 订单等待超时时间（秒），默认60
    require_confirmation: bool = True  # 是否需要二次确认，默认True
    signal_skip_fee: float = 2.0  # 跳过费（美元），默认2
    signal_timeout_minutes: int = 5  # 跳过超时时间（分钟），默认5分钟


@dataclass
class Signal:
    """交易信号"""
    signal_id: str  # 唯一信号ID
    timestamp: float  # 信号时间戳（Unix时间戳）
    type: str = "ORDER"  # 信号类型
    action: str = ""  # BUY/SELL
    symbol: str = ""  # 期权代码
    quantity: int = 0  # 合约数量
    order_type: str = "LMT"  # 订单类型：LMT/MKT
    limit_price: Optional[float] = None  # 限价
    time_in_force: str = "DAY"  # DAY/GTC
    strategy: Optional[str] = None  # 策略类型
    legs: Optional[List[OptionLeg]] = None  # 组合订单的腿
    metadata: Optional[Dict[str, Any]] = None  # 元数据
    signal_category: Optional[str] = None  # 信号类别：TRADE/SMART_MONEY/UNUSUAL_ACTIVITY/ALERT
    signal_subtype: Optional[str] = None  # 信号子类型：OPEN/CLOSE/WHALE_BUY等
    asset_class: Optional[str] = None  # 资产类型：SPX_OPTIONS/CRYPTO/PREDICTION等
    auto_trade_enabled: bool = True  # 是否支持自动交易
    execution_config: Optional[ExecutionConfig] = None  # 订单执行配置（由后端下发）
    
    # 处理状态
    status: SignalStatus = SignalStatus.PENDING
    validation_result: Optional[str] = None  # 验证结果
    execution_result: Optional[str] = None  # 执行结果
    order_id: Optional[str] = None  # 订单ID
    error_message: Optional[str] = None  # 错误信息
    
    # 订单状态（新增）
    order_status: Optional[str] = None  # 标准化订单状态：NEW/SUBMITTED/PENDING/FILLED/CANCELLED/REJECTED/EXPIRED
    order_status_raw: Optional[str] = None  # 券商原始订单状态（用于调试）
    retry_count: int = 0  # 当前重试次数
    max_retry: int = 5  # 最大重试次数
    
    # 成交信息（新增）
    filled_price: Optional[float] = None  # 成交价
    filled_order_type: Optional[str] = None  # 成交订单类型：LIMIT/MARKET
    filled_amount: Optional[float] = None  # 成交金额
    commission: Optional[float] = None  # 佣金
    fees: Optional[float] = None  # 其他费用（税费等）
    realized_pnl: Optional[float] = None  # 已实现盈亏（平仓时有值）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        result = {
            "signal_id": self.signal_id,
            "timestamp": self.timestamp,
            "type": self.type,
            "action": self.action,
            "symbol": self.symbol,
            "quantity": self.quantity,
            "order_type": self.order_type,
            "limit_price": self.limit_price,
            "time_in_force": self.time_in_force,
            "strategy": self.strategy,
            "legs": [{"symbol": leg.symbol, "action": leg.action, 
                     "quantity": leg.quantity, "limit_price": leg.limit_price,
                     "strike": leg.strike, "option_type": leg.option_type}
                    for leg in (self.legs or [])],
            "metadata": self.metadata,
            "signal_category": self.signal_category,
            "signal_subtype": self.signal_subtype,
            "auto_trade_enabled": self.auto_trade_enabled,
            "status": self.status.value,
            "validation_result": self.validation_result,
            "execution_result": self.execution_result,
            "order_id": self.order_id,
            "error_message": self.error_message,
            "order_status": self.order_status,
            "order_status_raw": self.order_status_raw,
            "retry_count": self.retry_count,
            "max_retry": self.max_retry,
            "filled_price": self.filled_price,
            "filled_order_type": self.filled_order_type,
            "filled_amount": self.filled_amount,
            "commission": self.commission,
            "fees": self.fees,
            "realized_pnl": self.realized_pnl
        }
        
        # 添加执行配置（如果有）
        if self.execution_config:
            result["execution_config"] = {
                "max_retry_attempts": self.execution_config.max_retry_attempts,
                "limit_order_attempts": self.execution_config.limit_order_attempts,
                "order_wait_timeout": self.execution_config.order_wait_timeout,
                "require_confirmation": self.execution_config.require_confirmation,
                "signal_skip_fee": self.execution_config.signal_skip_fee,
                "signal_timeout_minutes": self.execution_config.signal_timeout_minutes
            }
        
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Signal":
        """从字典创建"""
        legs = None
        if data.get("legs"):
            legs = [OptionLeg(**leg) for leg in data["legs"]]
        
        # 解析执行配置（如果有）
        execution_config = None
        if data.get("execution_config"):
            exec_cfg = data["execution_config"]
            execution_config = ExecutionConfig(
                max_retry_attempts=exec_cfg.get("max_retry_attempts", 5),
                limit_order_attempts=exec_cfg.get("limit_order_attempts", 1),
                order_wait_timeout=exec_cfg.get("order_wait_timeout", 10),
                require_confirmation=exec_cfg.get("require_confirmation", True),
                signal_skip_fee=exec_cfg.get("signal_skip_fee", 2.0),
                signal_timeout_minutes=exec_cfg.get("signal_timeout_minutes", 5)
            )
        
        return cls(
            signal_id=data["signal_id"],
            timestamp=data["timestamp"],
            type=data.get("type", "ORDER"),
            action=data.get("action", ""),
            symbol=data.get("symbol", ""),
            quantity=data.get("quantity", 0),
            order_type=data.get("order_type", "LMT"),
            limit_price=data.get("limit_price"),
            time_in_force=data.get("time_in_force", "DAY"),
            strategy=data.get("strategy"),
            legs=legs,
            metadata=data.get("metadata"),
            signal_category=data.get("signal_category"),
            signal_subtype=data.get("signal_subtype"),
            asset_class=data.get("asset_class"),
            auto_trade_enabled=data.get("auto_trade_enabled", True),
            execution_config=execution_config,
            status=SignalStatus(data.get("status", "pending")),
            validation_result=data.get("validation_result"),
            execution_result=data.get("execution_result"),
            order_id=data.get("order_id"),
            error_message=data.get("error_message"),
            order_status=data.get("order_status"),
            order_status_raw=data.get("order_status_raw"),
            retry_count=data.get("retry_count", 0),
            max_retry=data.get("max_retry", 5),
            filled_price=data.get("filled_price"),
            filled_order_type=data.get("filled_order_type"),
            filled_amount=data.get("filled_amount"),
            commission=data.get("commission"),
            fees=data.get("fees"),
            realized_pnl=data.get("realized_pnl")
        )
