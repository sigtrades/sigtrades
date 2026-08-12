"""执行器注册表：broker -> executor 类。"""

from typing import Dict, Optional, Type

from sigtrades_agent.executors.base import BrokerExecutor

_REGISTRY: Dict[str, Type[BrokerExecutor]] = {}


def register(broker: str, cls: Type[BrokerExecutor]) -> None:
    _REGISTRY[broker] = cls


def get_executor_class(broker: str) -> Optional[Type[BrokerExecutor]]:
    return _REGISTRY.get(broker)


def _autoload():
    """按需导入券商执行器（缺少 SDK 时不致整体崩溃）。"""
    try:
        from sigtrades_agent.executors.ibkr_executor import IBKRExecutor
        register("ibkr", IBKRExecutor)
    except Exception:  # noqa: BLE001
        pass
    try:
        from sigtrades_agent.executors.futu_executor import FutuExecutor
        register("futu", FutuExecutor)
    except Exception:  # noqa: BLE001
        pass


_autoload()

__all__ = ["BrokerExecutor", "register", "get_executor_class"]
