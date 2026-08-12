"""IBKR 执行器：专属事件循环线程承载 ib_async。

ib_async 要求创建 IB() 及其后续所有调用都在同一个绑定了事件循环的线程内完成。
BrokerExecutor 基类天然单线程（run/connect/execute 都在本执行器线程），这里只需在
线程启动时为本线程创建并设置一个独立的 asyncio 事件循环。

连接参数（host/port/client_id）仅来自本机配置；交易账户由网页下发的 account_id 决定。
"""

from __future__ import annotations

import asyncio
import logging

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_agent.executors.base import BrokerExecutor

logger = logging.getLogger(__name__)


class IBKRExecutor(BrokerExecutor):
    broker = "ibkr"

    def _thread_setup(self) -> None:
        # 为本执行器线程创建专属事件循环（ib_async 单线程约束）
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            logger.info("[ibkr] 已为执行器线程创建专属事件循环")

    def _create_adapter(self) -> BaseBrokerAdapter:
        from sigtrades_core.brokers.ibkr import get_ibkr_adapter

        cfg = dict(self.profile.config or {})
        # 端口默认 7497(TWS 模拟)，host 默认本机；实盘 7496
        cfg.setdefault("host", "127.0.0.1")
        cfg.setdefault("port", 7497)
        cfg.setdefault("client_id", 1)
        # 不在此固化 account：由执行消息里的网页 account_id 在下单前写入 adapter
        cfg.pop("account", None)
        adapter_cls = get_ibkr_adapter()
        return adapter_cls(cfg)
