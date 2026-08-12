#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
订单状态定义
Order Status Definitions - 跨券商通用的标准化订单状态
"""

from enum import Enum
from typing import Dict
from dataclasses import dataclass


class OrderStatus(Enum):
    """标准化订单状态（跨券商通用）"""
    
    # 初始状态
    NEW = "NEW"                      # 订单初始状态（刚创建）
    
    # 进行中状态
    SUBMITTED = "SUBMITTED"          # 已提交（等待确认）
    PENDING = "PENDING"              # 待成交（已确认，等待成交）
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交
    
    # 终态 - 成功
    FILLED = "FILLED"                # 完全成交
    
    # 终态 - 失败/取消
    CANCELLED = "CANCELLED"          # 已取消
    REJECTED = "REJECTED"            # 已拒绝
    EXPIRED = "EXPIRED"              # 已过期/无效
    
    # 特殊状态
    UNKNOWN = "UNKNOWN"              # 未知状态


@dataclass
class OrderStatusInfo:
    """订单状态显示信息"""
    status: OrderStatus
    label_cn: str           # 中文标签
    label_en: str           # 英文标签
    color: str              # 显示颜色 (hex)
    bg_color: str           # 背景颜色 (hex)
    is_terminal: bool       # 是否终态
    is_success: bool        # 是否成功终态
    priority: int           # 排序优先级（越小越重要）


# 状态显示配置
ORDER_STATUS_CONFIG: Dict[OrderStatus, OrderStatusInfo] = {
    OrderStatus.NEW: OrderStatusInfo(
        status=OrderStatus.NEW,
        label_cn="新建",
        label_en="New",
        color="#757575",
        bg_color="#f5f5f5",
        is_terminal=False,
        is_success=False,
        priority=10
    ),
    OrderStatus.SUBMITTED: OrderStatusInfo(
        status=OrderStatus.SUBMITTED,
        label_cn="已提交",
        label_en="Submitted",
        color="#1976d2",
        bg_color="#e3f2fd",
        is_terminal=False,
        is_success=False,
        priority=20
    ),
    OrderStatus.PENDING: OrderStatusInfo(
        status=OrderStatus.PENDING,
        label_cn="待成交",
        label_en="Pending",
        color="#f57c00",
        bg_color="#fff3e0",
        is_terminal=False,
        is_success=False,
        priority=30
    ),
    OrderStatus.PARTIALLY_FILLED: OrderStatusInfo(
        status=OrderStatus.PARTIALLY_FILLED,
        label_cn="部分成交",
        label_en="Partial",
        color="#689f38",
        bg_color="#f1f8e9",
        is_terminal=False,
        is_success=False,
        priority=40
    ),
    OrderStatus.FILLED: OrderStatusInfo(
        status=OrderStatus.FILLED,
        label_cn="已成交",
        label_en="Filled",
        color="#388e3c",
        bg_color="#e8f5e9",
        is_terminal=True,
        is_success=True,
        priority=50
    ),
    OrderStatus.CANCELLED: OrderStatusInfo(
        status=OrderStatus.CANCELLED,
        label_cn="已取消",
        label_en="Cancelled",
        color="#757575",
        bg_color="#eeeeee",
        is_terminal=True,
        is_success=False,
        priority=60
    ),
    OrderStatus.REJECTED: OrderStatusInfo(
        status=OrderStatus.REJECTED,
        label_cn="已拒绝",
        label_en="Rejected",
        color="#d32f2f",
        bg_color="#ffebee",
        is_terminal=True,
        is_success=False,
        priority=70
    ),
    OrderStatus.EXPIRED: OrderStatusInfo(
        status=OrderStatus.EXPIRED,
        label_cn="已过期",
        label_en="Expired",
        color="#5d4037",
        bg_color="#efebe9",
        is_terminal=True,
        is_success=False,
        priority=80
    ),
    OrderStatus.UNKNOWN: OrderStatusInfo(
        status=OrderStatus.UNKNOWN,
        label_cn="未知",
        label_en="Unknown",
        color="#546e7a",
        bg_color="#eceff1",
        is_terminal=False,
        is_success=False,
        priority=100
    ),
}


def get_status_info(status: OrderStatus) -> OrderStatusInfo:
    """获取状态显示信息"""
    return ORDER_STATUS_CONFIG.get(status, ORDER_STATUS_CONFIG[OrderStatus.UNKNOWN])


def get_status_from_string(status_str: str) -> OrderStatus:
    """从字符串获取状态枚举（支持中英文）"""
    if not status_str:
        return OrderStatus.UNKNOWN
    
    # 先尝试直接匹配英文
    try:
        return OrderStatus(status_str.upper())
    except ValueError:
        pass
    
    # 中文状态映射
    cn_status_map = {
        "新建": OrderStatus.NEW,
        "已提交": OrderStatus.SUBMITTED,
        "待成交": OrderStatus.PENDING,
        "部分成交": OrderStatus.PARTIALLY_FILLED,
        "已成交": OrderStatus.FILLED,
        "全部成交": OrderStatus.FILLED,
        "已取消": OrderStatus.CANCELLED,
        "已撤单": OrderStatus.CANCELLED,
        "已拒绝": OrderStatus.REJECTED,
        "被拒绝": OrderStatus.REJECTED,
        "已过期": OrderStatus.EXPIRED,
        "无效": OrderStatus.EXPIRED,
    }
    
    return cn_status_map.get(status_str, OrderStatus.UNKNOWN)


def is_terminal_status(status: OrderStatus) -> bool:
    """判断是否为终态"""
    info = get_status_info(status)
    return info.is_terminal


def is_success_status(status: OrderStatus) -> bool:
    """判断是否为成功终态"""
    info = get_status_info(status)
    return info.is_success
