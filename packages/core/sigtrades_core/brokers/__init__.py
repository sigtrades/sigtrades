"""券商适配器工厂。

统一通过 `create_broker_adapter(name, config)` 创建适配器，下游（execution_core /
Agent / cloud-executor）不直接 import 具体券商类，保持对券商无感知。
"""

from typing import Any, Dict

from sigtrades_core.brokers.base import BaseBrokerAdapter

# 券商标识 -> 部署侧（cloud=云端执行，gateway=本地 Agent 执行）
BROKER_DEPLOYMENT = {
    "tiger": "cloud",
    "longbridge": "cloud",
    "schwab": "cloud",
    "alpaca": "cloud",
    "usmart": "cloud",
    "ibkr_web": "cloud",
    "ibkr": "gateway",
    "futu": "gateway",
}


def create_broker_adapter(name: str, config: Dict[str, Any]) -> BaseBrokerAdapter:
    """根据券商名创建适配器实例（延迟导入，避免无关 SDK 依赖被强制加载）。"""
    key = (name or "").strip().lower()
    if key in ("tiger", "老虎", "老虎证券", "tigersecurities"):
        from sigtrades_core.brokers.tiger.adapter import TigerBrokerAdapter
        return TigerBrokerAdapter(config)
    if key in ("ibkr_web", "ibkr-web", "ibkrweb"):
        from sigtrades_core.brokers.ibkr_web import IbkrWebBrokerAdapter
        return IbkrWebBrokerAdapter(config)
    if key in ("ibkr", "ib", "interactive brokers", "interactivebrokers"):
        from sigtrades_core.brokers.ibkr import get_ibkr_adapter
        return get_ibkr_adapter()(config)
    if key in ("futu", "富途", "富途证券"):
        from sigtrades_core.brokers.futu.adapter import FutuBrokerAdapter
        return FutuBrokerAdapter(config)
    if key in ("longbridge", "长桥", "长桥证券", "longport"):
        from sigtrades_core.brokers.longbridge.adapter import LongbridgeBrokerAdapter
        return LongbridgeBrokerAdapter(config)
    if key in ("schwab", "charles schwab", "charlesschwab", "嘉信", "嘉信理财"):
        from sigtrades_core.brokers.schwab.adapter import SchwabBrokerAdapter
        return SchwabBrokerAdapter(config)
    if key in ("alpaca", "alpaca markets"):
        from sigtrades_core.brokers.alpaca.adapter import AlpacaBrokerAdapter
        return AlpacaBrokerAdapter(config)
    if key in ("usmart", "盈立", "盈立证券", "usmart securities", "yingsmart"):
        from sigtrades_core.brokers.usmart.adapter import UsmartBrokerAdapter
        return UsmartBrokerAdapter(config)
    raise ValueError(f"未知券商: {name}")


def deployment_for(name: str) -> str:
    """返回券商的部署侧：'cloud'（云端执行）或 'gateway'（本地 Agent 执行）。"""
    return BROKER_DEPLOYMENT.get((name or "").strip().lower(), "gateway")
