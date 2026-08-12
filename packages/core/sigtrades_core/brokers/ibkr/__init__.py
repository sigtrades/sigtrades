#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IBKR (Interactive Brokers) 适配器模块
"""

# 延迟导入，避免模块级别导入 ib_async 时的事件循环问题
def get_ibkr_adapter():
    """获取 IBKR 适配器类（延迟导入）"""
    from .adapter import IBKRBrokerAdapter
    return IBKRBrokerAdapter

__all__ = ['get_ibkr_adapter']
