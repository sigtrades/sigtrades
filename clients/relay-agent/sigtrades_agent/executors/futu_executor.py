"""富途执行器：普通 worker 线程承载 OpenD 连接。

OpenD 网关默认监听 127.0.0.1:11111；支持多 gateway profile（不同 host/port/trd_env），
由 Agent 为每个富途 profile 起一个独立执行器线程。连接仅本机；交易账户由网页下发。
"""

from __future__ import annotations

import logging

from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_agent.executors.base import BrokerExecutor

logger = logging.getLogger(__name__)


class FutuExecutor(BrokerExecutor):
    broker = "futu"

    def _create_adapter(self) -> BaseBrokerAdapter:
        from sigtrades_core.brokers.futu.adapter import FutuBrokerAdapter

        cfg = dict(self.profile.config or {})
        cfg.setdefault("host", "127.0.0.1")
        cfg.setdefault("port", 11111)
        cfg.setdefault("env", cfg.get("trd_env", "SIMULATE"))
        cfg.pop("account", None)
        return FutuBrokerAdapter(cfg)
