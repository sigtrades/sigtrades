"""连接器注册表 + 生命周期管理。"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Type

from sigtrades_core.sources.base import BaseSignalSource

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[BaseSignalSource]] = {}


def register(kind: str, cls: Type[BaseSignalSource]) -> None:
    _REGISTRY[kind] = cls


def get_connector(kind: str) -> Optional[Type[BaseSignalSource]]:
    return _REGISTRY.get(kind)


def _autoload():
    try:
        from app.connectors.discord import DiscordConnector
        register("discord", DiscordConnector)
    except Exception as e:
        logger.warning("Discord connector load failed: %s", e)
    try:
        from app.connectors.webhook_source import WebhookConnector
        register("webhook", WebhookConnector)
    except Exception as e:
        logger.warning("Webhook connector load failed: %s", e)
    try:
        from app.connectors.tradingview import TradingViewConnector
        register("tradingview", TradingViewConnector)
    except Exception as e:
        logger.warning("TradingView connector load failed: %s", e)
    try:
        from app.connectors.telegram import TelegramConnector
        register("telegram", TelegramConnector)
    except Exception as e:
        logger.warning("Telegram connector load failed: %s", e)


_autoload()
