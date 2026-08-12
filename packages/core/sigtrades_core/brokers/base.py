#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
券商适配器抽象基类
Base Broker Adapter Abstract Class
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from sigtrades_core.signal.models import Signal


class BaseBrokerAdapter(ABC):
    """
    券商适配器抽象基类
    定义了所有券商适配器需要实现的统一接口
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化适配器
        
        Args:
            config: 券商配置
        """
        self.config = config
        self.connected = False
        self.connect_error: Optional[str] = None
    
    @abstractmethod
    def connect(self) -> bool:
        """连接到券商 API"""
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """断开与券商 API 的连接"""
        pass
    
    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """获取账户信息（余额、持仓等）"""
        pass
    
    @abstractmethod
    def get_option_positions(self) -> List[Dict[str, Any]]:
        """获取期权持仓列表"""
        pass
    
    @abstractmethod
    def place_order(self, signal: Signal) -> Dict[str, Any]:
        """
        提交订单（单个期权或组合订单）
        
        Args:
            signal: 交易信号
            
        Returns:
            订单结果 {"order_id": "...", "status": "SUCCESS/FAILED", "error": "..."}
        """
        pass
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:
        """撤销订单"""
        pass
    
    @abstractmethod
    def get_orders(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询订单列表"""
        pass
    
    @abstractmethod
    def supports_combined_order(self) -> bool:
        """是否支持组合下单"""
        pass
    
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self.connected

    def place_protective_orders(
        self,
        signal: Signal,
        fill_price: float,
        *,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
    ) -> Dict[str, Any]:
        """成交后挂止损/止盈（子类可覆盖）。"""
        return {"status": "skipped"}
