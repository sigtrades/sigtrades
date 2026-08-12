#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
券商订单状态映射
Broker Order Status Mapping - 各券商状态到标准状态的映射
"""

from typing import Dict, Optional, Type
from sigtrades_core.trading.order_status import OrderStatus


# ============================================================
# Tiger 证券状态映射
# ============================================================

# Tiger 状态码 -> 标准状态
TIGER_STATUS_CODE_MAP: Dict[int, OrderStatus] = {
    -2: OrderStatus.EXPIRED,           # Invalid - 非法状态
    -1: OrderStatus.NEW,               # Initial - 订单初始状态
    2: OrderStatus.PARTIALLY_FILLED,   # PartiallyFilled - 部分成交
    4: OrderStatus.CANCELLED,          # Cancelled - 已取消
    5: OrderStatus.SUBMITTED,          # Submitted/Held - 已提交
    6: OrderStatus.FILLED,             # Filled - 完全成交
    7: OrderStatus.REJECTED,           # Inactive - 已失效
    8: OrderStatus.PARTIALLY_FILLED,   # PartiallyFilled - 部分成交（另一状态码）
}

# Tiger 状态字符串 -> 标准状态
TIGER_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    # Tiger API 返回的状态字符串
    "Invalid": OrderStatus.EXPIRED,
    "Initial": OrderStatus.NEW,
    "PartiallyFilled": OrderStatus.PARTIALLY_FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Submitted": OrderStatus.SUBMITTED,
    "Held": OrderStatus.SUBMITTED,
    "Filled": OrderStatus.FILLED,
    "Inactive": OrderStatus.REJECTED,
    
    # 大写形式（兼容）
    "INVALID": OrderStatus.EXPIRED,
    "INITIAL": OrderStatus.NEW,
    "PARTIALLYFILLED": OrderStatus.PARTIALLY_FILLED,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "SUBMITTED": OrderStatus.SUBMITTED,
    "HELD": OrderStatus.SUBMITTED,
    "FILLED": OrderStatus.FILLED,
    "INACTIVE": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
    "NEW": OrderStatus.NEW,
    "REJECTED": OrderStatus.REJECTED,
}


class BrokerStatusMapper:
    """券商状态映射器基类"""
    
    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        """将券商状态转换为标准状态"""
        raise NotImplementedError
    
    @staticmethod
    def from_standard(standard_status: OrderStatus):
        """将标准状态转换为券商状态"""
        raise NotImplementedError


class TigerStatusMapper(BrokerStatusMapper):
    """老虎证券状态映射器"""
    
    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        """
        将Tiger订单状态转换为标准状态
        
        Args:
            broker_status: Tiger订单状态（int, str, 或 Enum）
        
        Returns:
            标准订单状态
        """
        if broker_status is None:
            return OrderStatus.UNKNOWN
        
        # 处理 Tiger OrderStatus 枚举
        if hasattr(broker_status, 'value'):
            broker_status = broker_status.value
        
        # 处理整数状态码
        if isinstance(broker_status, int):
            return TIGER_STATUS_CODE_MAP.get(broker_status, OrderStatus.UNKNOWN)
        
        # 处理字符串状态
        if isinstance(broker_status, str):
            # 直接匹配
            if broker_status in TIGER_STATUS_STR_MAP:
                return TIGER_STATUS_STR_MAP[broker_status]
            
            # 大写匹配
            upper_status = broker_status.upper()
            if upper_status in TIGER_STATUS_STR_MAP:
                return TIGER_STATUS_STR_MAP[upper_status]
            
            # 尝试解析为整数
            try:
                status_int = int(broker_status)
                return TIGER_STATUS_CODE_MAP.get(status_int, OrderStatus.UNKNOWN)
            except ValueError:
                pass
        
        return OrderStatus.UNKNOWN
    
    @staticmethod
    def from_standard(standard_status: OrderStatus) -> int:
        """将标准状态转换为Tiger状态码"""
        reverse_map = {v: k for k, v in TIGER_STATUS_CODE_MAP.items()}
        return reverse_map.get(standard_status, -1)


# ============================================================
# IBKR (Interactive Brokers) 状态映射
# ============================================================

# IBKR 状态字符串 -> 标准状态
IBKR_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    # IBKR API 返回的状态字符串
    "Submitted": OrderStatus.SUBMITTED,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "Inactive": OrderStatus.REJECTED,
    "PendingSubmit": OrderStatus.PENDING,
    "PreSubmitted": OrderStatus.PENDING,
    "PendingCancel": OrderStatus.PENDING,
    "ApiCancelled": OrderStatus.CANCELLED,
    "ApiPending": OrderStatus.PENDING,
    
    # 大写形式（兼容）
    "SUBMITTED": OrderStatus.SUBMITTED,
    "FILLED": OrderStatus.FILLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "INACTIVE": OrderStatus.REJECTED,
    "PENDINGSUBMIT": OrderStatus.PENDING,
    "PRESUBMITTED": OrderStatus.PENDING,
    "PENDINGCANCEL": OrderStatus.PENDING,
    "APICANCELLED": OrderStatus.CANCELLED,
    "APIPENDING": OrderStatus.PENDING,
}


class IBKRStatusMapper(BrokerStatusMapper):
    """IBKR (Interactive Brokers) 状态映射器"""
    
    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        """
        将IBKR订单状态转换为标准状态
        
        Args:
            broker_status: IBKR订单状态（str）
        
        Returns:
            标准订单状态
        """
        if broker_status is None:
            return OrderStatus.UNKNOWN
        
        # 处理字符串状态
        if isinstance(broker_status, str):
            # 直接匹配
            if broker_status in IBKR_STATUS_STR_MAP:
                return IBKR_STATUS_STR_MAP[broker_status]
            
            # 大写匹配
            upper_status = broker_status.upper()
            if upper_status in IBKR_STATUS_STR_MAP:
                return IBKR_STATUS_STR_MAP[upper_status]
        
        return OrderStatus.UNKNOWN
    
    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        """将标准状态转换为IBKR状态字符串"""
        reverse_map = {
            OrderStatus.SUBMITTED: "Submitted",
            OrderStatus.FILLED: "Filled",
            OrderStatus.CANCELLED: "Cancelled",
            OrderStatus.REJECTED: "Inactive",
            OrderStatus.PENDING: "PendingSubmit",
            OrderStatus.NEW: "PendingSubmit",
        }
        return reverse_map.get(standard_status, "Unknown")


# ============================================================
# 富途证券状态映射
# ============================================================

FUTU_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    "NONE": OrderStatus.UNKNOWN,
    "UNSUBMITTED": OrderStatus.NEW,
    "WAITING_SUBMIT": OrderStatus.NEW,
    "SUBMITTING": OrderStatus.PENDING,
    "SUBMIT_FAILED": OrderStatus.REJECTED,
    "TIMEOUT": OrderStatus.EXPIRED,
    "SUBMITTED": OrderStatus.SUBMITTED,
    "FILLED_PART": OrderStatus.PARTIALLY_FILLED,
    "FILLED_ALL": OrderStatus.FILLED,
    "CANCELLING_PART": OrderStatus.PENDING,
    "CANCELLING_ALL": OrderStatus.PENDING,
    "CANCELLED_PART": OrderStatus.CANCELLED,
    "CANCELLED_ALL": OrderStatus.CANCELLED,
    "FAILED": OrderStatus.REJECTED,
    "DISABLED": OrderStatus.REJECTED,
    "DELETED": OrderStatus.CANCELLED,
}


class FutuStatusMapper(BrokerStatusMapper):
    """富途证券状态映射器"""

    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        if broker_status is None:
            return OrderStatus.UNKNOWN
        if hasattr(broker_status, 'name'):
            broker_status = broker_status.name
        status_str = str(broker_status).upper()
        return FUTU_STATUS_STR_MAP.get(status_str, OrderStatus.UNKNOWN)

    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        reverse_map = {
            OrderStatus.SUBMITTED: "SUBMITTED",
            OrderStatus.FILLED: "FILLED_ALL",
            OrderStatus.CANCELLED: "CANCELLED_ALL",
            OrderStatus.REJECTED: "FAILED",
            OrderStatus.PENDING: "SUBMITTING",
            OrderStatus.NEW: "UNSUBMITTED",
            OrderStatus.PARTIALLY_FILLED: "FILLED_PART",
            OrderStatus.EXPIRED: "TIMEOUT",
        }
        return reverse_map.get(standard_status, "NONE")


# ============================================================
# 长桥证券状态映射
# ============================================================

LONGBRIDGE_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    "New": OrderStatus.NEW,
    "WaitToNew": OrderStatus.PENDING,
    "NotReported": OrderStatus.SUBMITTED,
    "ProtectedNotReported": OrderStatus.SUBMITTED,
    "VarietiesNotReported": OrderStatus.SUBMITTED,
    "PartialFilled": OrderStatus.PARTIALLY_FILLED,
    "Filled": OrderStatus.FILLED,
    "WaitToCancel": OrderStatus.PENDING,
    "PendingCancel": OrderStatus.PENDING,
    "Canceled": OrderStatus.CANCELLED,
    "Rejected": OrderStatus.REJECTED,
    "Expired": OrderStatus.EXPIRED,
    "PartialWithdrawal": OrderStatus.PARTIALLY_FILLED,
    "PendingReplace": OrderStatus.PENDING,
    "WaitToReplace": OrderStatus.PENDING,
    "Replaced": OrderStatus.SUBMITTED,
    "ReplacedNotReported": OrderStatus.SUBMITTED,
    "Unknown": OrderStatus.UNKNOWN,
    # order_detail / WebSocket 推送使用的 *Status 后缀（见长桥 OpenAPI 文档）
    "NewStatus": OrderStatus.NEW,
    "FilledStatus": OrderStatus.FILLED,
    "PartialFilledStatus": OrderStatus.PARTIALLY_FILLED,
    "RejectedStatus": OrderStatus.REJECTED,
    "CanceledStatus": OrderStatus.CANCELLED,
    "ExpiredStatus": OrderStatus.EXPIRED,
    "PendingCancelStatus": OrderStatus.PENDING,
    "PendingReplaceStatus": OrderStatus.PENDING,
    "ReplacedStatus": OrderStatus.SUBMITTED,
}


class LongbridgeStatusMapper(BrokerStatusMapper):
    """长桥证券状态映射器"""

    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        if broker_status is None:
            return OrderStatus.UNKNOWN
        if hasattr(broker_status, "name"):
            broker_status = broker_status.name
        elif hasattr(broker_status, "value"):
            broker_status = broker_status.value
        status_str = str(broker_status)
        if status_str in LONGBRIDGE_STATUS_STR_MAP:
            return LONGBRIDGE_STATUS_STR_MAP[status_str]
        if status_str.endswith("Status"):
            trimmed = status_str[:-6]
            if trimmed in LONGBRIDGE_STATUS_STR_MAP:
                return LONGBRIDGE_STATUS_STR_MAP[trimmed]
        upper = status_str.upper()
        for key, val in LONGBRIDGE_STATUS_STR_MAP.items():
            if key.upper() == upper:
                return val
        return OrderStatus.UNKNOWN

    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        reverse_map = {
            OrderStatus.NEW: "New",
            OrderStatus.PENDING: "WaitToNew",
            OrderStatus.SUBMITTED: "NotReported",
            OrderStatus.PARTIALLY_FILLED: "PartialFilled",
            OrderStatus.FILLED: "Filled",
            OrderStatus.CANCELLED: "Canceled",
            OrderStatus.REJECTED: "Rejected",
            OrderStatus.EXPIRED: "Expired",
        }
        return reverse_map.get(standard_status, "Unknown")


# ============================================================
# Charles Schwab Trader API 状态映射
# ============================================================

SCHWAB_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    "AWAITING_PARENT_ORDER": OrderStatus.PENDING,
    "AWAITING_CONDITION": OrderStatus.PENDING,
    "AWAITING_STOP_CONDITION": OrderStatus.PENDING,
    "AWAITING_MANUAL_REVIEW": OrderStatus.PENDING,
    "ACCEPTED": OrderStatus.SUBMITTED,
    "AWAITING_UR_OUT": OrderStatus.PENDING,
    "PENDING_ACTIVATION": OrderStatus.PENDING,
    "QUEUED": OrderStatus.SUBMITTED,
    "WORKING": OrderStatus.SUBMITTED,
    "PENDING_CANCEL": OrderStatus.PENDING,
    "PENDING_REPLACE": OrderStatus.PENDING,
    "PENDING_ACKNOWLEDGEMENT": OrderStatus.PENDING,
    "PENDING_RECALL": OrderStatus.PENDING,
    "REPLACED": OrderStatus.SUBMITTED,
    "FILLED": OrderStatus.FILLED,
    "CANCELED": OrderStatus.CANCELLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "REJECTED": OrderStatus.REJECTED,
    "EXPIRED": OrderStatus.EXPIRED,
    "NEW": OrderStatus.NEW,
}


class SchwabStatusMapper(BrokerStatusMapper):
    """Charles Schwab Trader API 状态映射器。"""

    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        if broker_status is None:
            return OrderStatus.UNKNOWN
        if hasattr(broker_status, "value"):
            broker_status = broker_status.value
        return SCHWAB_STATUS_STR_MAP.get(
            str(broker_status).strip().upper(),
            OrderStatus.UNKNOWN,
        )

    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        reverse_map = {
            OrderStatus.NEW: "NEW",
            OrderStatus.PENDING: "PENDING_ACTIVATION",
            OrderStatus.SUBMITTED: "WORKING",
            OrderStatus.PARTIALLY_FILLED: "WORKING",
            OrderStatus.FILLED: "FILLED",
            OrderStatus.CANCELLED: "CANCELED",
            OrderStatus.REJECTED: "REJECTED",
            OrderStatus.EXPIRED: "EXPIRED",
        }
        return reverse_map.get(standard_status, "UNKNOWN")


# ============================================================
# Alpaca Trading API 状态映射
# ============================================================

ALPACA_STATUS_STR_MAP: Dict[str, OrderStatus] = {
    "NEW": OrderStatus.NEW,
    "PENDING_NEW": OrderStatus.PENDING,
    "ACCEPTED": OrderStatus.SUBMITTED,
    "ACCEPTED_FOR_BIDDING": OrderStatus.SUBMITTED,
    "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
    "FILLED": OrderStatus.FILLED,
    "DONE_FOR_DAY": OrderStatus.EXPIRED,
    "CANCELED": OrderStatus.CANCELLED,
    "CANCELLED": OrderStatus.CANCELLED,
    "EXPIRED": OrderStatus.EXPIRED,
    "REPLACED": OrderStatus.SUBMITTED,
    "PENDING_CANCEL": OrderStatus.PENDING,
    "PENDING_REPLACE": OrderStatus.PENDING,
    "STOPPED": OrderStatus.REJECTED,
    "REJECTED": OrderStatus.REJECTED,
    "SUSPENDED": OrderStatus.PENDING,
    "CALCULATED": OrderStatus.PENDING,
    "HELD": OrderStatus.PENDING,
}


class AlpacaStatusMapper(BrokerStatusMapper):
    """Alpaca Trading API 状态映射器。"""

    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        if broker_status is None:
            return OrderStatus.UNKNOWN
        if hasattr(broker_status, "value"):
            broker_status = broker_status.value
        return ALPACA_STATUS_STR_MAP.get(
            str(broker_status).strip().upper(),
            OrderStatus.UNKNOWN,
        )

    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        reverse_map = {
            OrderStatus.NEW: "new",
            OrderStatus.PENDING: "pending_new",
            OrderStatus.SUBMITTED: "accepted",
            OrderStatus.PARTIALLY_FILLED: "partially_filled",
            OrderStatus.FILLED: "filled",
            OrderStatus.CANCELLED: "canceled",
            OrderStatus.REJECTED: "rejected",
            OrderStatus.EXPIRED: "expired",
        }
        return reverse_map.get(standard_status, "unknown")


# ============================================================
# uSMART / 盈立状态映射
# ============================================================

USMART_STATUS_NAME_MAP: Dict[str, OrderStatus] = {
    "等待提交": OrderStatus.PENDING,
    "待报": OrderStatus.PENDING,
    "待报单": OrderStatus.PENDING,
    "已报": OrderStatus.SUBMITTED,
    "已报待撤": OrderStatus.PENDING,
    "部成待撤": OrderStatus.PARTIALLY_FILLED,
    "部撤": OrderStatus.CANCELLED,
    "已撤": OrderStatus.CANCELLED,
    "已撤单": OrderStatus.CANCELLED,
    "部成": OrderStatus.PARTIALLY_FILLED,
    "已成": OrderStatus.FILLED,
    "废单": OrderStatus.REJECTED,
    "拒绝": OrderStatus.REJECTED,
    "等待改单": OrderStatus.PENDING,
    "超时": OrderStatus.EXPIRED,
}

USMART_STATUS_CODE_MAP: Dict[int, OrderStatus] = {
    0: OrderStatus.PENDING,
    1: OrderStatus.PENDING,
    2: OrderStatus.SUBMITTED,
    3: OrderStatus.PENDING,
    4: OrderStatus.PARTIALLY_FILLED,
    5: OrderStatus.PENDING,
    6: OrderStatus.CANCELLED,
    7: OrderStatus.PARTIALLY_FILLED,
    8: OrderStatus.FILLED,
    9: OrderStatus.CANCELLED,
}


class UsmartStatusMapper(BrokerStatusMapper):
    """uSMART（盈立）委托状态映射。"""

    @staticmethod
    def to_standard(broker_status) -> OrderStatus:
        if broker_status is None:
            return OrderStatus.UNKNOWN
        if hasattr(broker_status, "value"):
            broker_status = broker_status.value
        text = str(broker_status).strip()
        if text in USMART_STATUS_NAME_MAP:
            return USMART_STATUS_NAME_MAP[text]
        try:
            code = int(float(text))
            if code in USMART_STATUS_CODE_MAP:
                return USMART_STATUS_CODE_MAP[code]
        except (TypeError, ValueError):
            pass
        upper = text.upper()
        for key, val in USMART_STATUS_NAME_MAP.items():
            if key.upper() == upper:
                return val
        return OrderStatus.UNKNOWN

    @staticmethod
    def from_standard(standard_status: OrderStatus) -> str:
        reverse_map = {
            OrderStatus.NEW: "等待提交",
            OrderStatus.PENDING: "等待提交",
            OrderStatus.SUBMITTED: "已报",
            OrderStatus.PARTIALLY_FILLED: "部成",
            OrderStatus.FILLED: "已成",
            OrderStatus.CANCELLED: "已撤",
            OrderStatus.REJECTED: "废单",
            OrderStatus.EXPIRED: "超时",
        }
        return reverse_map.get(standard_status, "未知")


# ============================================================
# 映射器注册表
# ============================================================

BROKER_STATUS_MAPPERS: Dict[str, Type[BrokerStatusMapper]] = {
    "tiger": TigerStatusMapper,
    "longbridge": LongbridgeStatusMapper,
    "schwab": SchwabStatusMapper,
    "alpaca": AlpacaStatusMapper,
    "usmart": UsmartStatusMapper,
    "ibkr": IBKRStatusMapper,
    "futu": FutuStatusMapper,
}


def get_status_mapper(broker_name: str) -> BrokerStatusMapper:
    """
    获取券商状态映射器
    
    Args:
        broker_name: 券商名称（如 'tiger', 'ibkr'）
    
    Returns:
        对应的状态映射器实例
    
    Raises:
        ValueError: 未知的券商名称
    """
    mapper_class = BROKER_STATUS_MAPPERS.get(broker_name.lower())
    if mapper_class:
        return mapper_class()
    raise ValueError(f"Unknown broker: {broker_name}")


def map_tiger_status(broker_status) -> OrderStatus:
    """
    快捷方法：将Tiger状态转换为标准状态
    
    Args:
        broker_status: Tiger订单状态
    
    Returns:
        标准订单状态
    """
    return TigerStatusMapper.to_standard(broker_status)


def map_ibkr_status(broker_status) -> OrderStatus:
    """
    快捷方法：将IBKR状态转换为标准状态
    
    Args:
        broker_status: IBKR订单状态
    
    Returns:
        标准订单状态
    """
    return IBKRStatusMapper.to_standard(broker_status)


def map_futu_status(broker_status) -> OrderStatus:
    """
    快捷方法：将Futu状态转换为标准状态
    
    Args:
        broker_status: Futu订单状态
    
    Returns:
        标准订单状态
    """
    return FutuStatusMapper.to_standard(broker_status)


def map_longbridge_status(broker_status) -> OrderStatus:
    """快捷方法：将长桥状态转换为标准状态。"""
    return LongbridgeStatusMapper.to_standard(broker_status)
