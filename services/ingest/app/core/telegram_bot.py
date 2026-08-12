"""Telegram Bot long-polling（合规 bot API）。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings
from app.connectors.telegram import TelegramConnector
from app.connectors.discord import normalized_to_inbound
from app.core.forward import forward_inbound

logger = logging.getLogger("telegram-bot")

API_BASE = "https://api.telegram.org"
_REFRESH_INTERVAL = 60.0


def _to_inbound(ns) -> Dict[str, Any]:
    return normalized_to_inbound(ns)


class TelegramBotRunner:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._sources: List[Dict[str, Any]] = []
        self._chat_map: Dict[str, Dict[str, Any]] = {}
        self._offset = 0
        self._last_refresh = 0.0

    async def run(self) -> None:
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.info("TELEGRAM_BOT_TOKEN 未配置，跳过 Telegram polling")
            return
        asyncio.create_task(self._refresh_loop())
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._poll_once()
                backoff = 2.0
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.warning("Telegram polling 错误: %s，%.0fs 后重试", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    def stop(self) -> None:
        self._stop.set()

    async def _refresh_loop(self) -> None:
        while not self._stop.is_set():
            await self._refresh_sources()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=_REFRESH_INTERVAL)
            except asyncio.TimeoutError:
                pass

    async def _refresh_sources(self) -> None:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
                resp = await client.get(
                    f"{settings.API_SERVER_URL}/internal/telegram-sources",
                    headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
                )
            resp.raise_for_status()
            self._sources = resp.json().get("sources", [])
            self._chat_map = {}
            for src in self._sources:
                for ch in src.get("chat_ids") or []:
                    self._chat_map[str(ch)] = src
            logger.info("Telegram 源刷新: %d sources, %d chats", len(self._sources), len(self._chat_map))
        except Exception as e:  # noqa: BLE001
            logger.warning("拉取 telegram-sources 失败: %s", e)

    async def _poll_once(self) -> None:
        token = settings.TELEGRAM_BOT_TOKEN
        url = f"{API_BASE}/bot{token}/getUpdates"
        params = {"timeout": 30, "offset": self._offset}
        async with httpx.AsyncClient(trust_env=False, timeout=35.0) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            raise RuntimeError(data.get("description", "telegram api error"))
        for upd in data.get("result", []):
            self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
            await process_telegram_update(upd, self._chat_map)

    async def ensure_sources(self) -> None:
        """Webhook 模式下按需刷新 chat 映射。"""
        import time
        if time.monotonic() - self._last_refresh > _REFRESH_INTERVAL or not self._chat_map:
            await self._refresh_sources()
            self._last_refresh = time.monotonic()
        return None


async def process_telegram_update(update: Dict[str, Any], chat_map: Dict[str, Dict[str, Any]]) -> int:
    """处理单条 Telegram Update，返回转发的信号数。"""
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return 0
    chat_id = str((msg.get("chat") or {}).get("id", ""))
    src = chat_map.get(chat_id)
    if not src:
        return 0
    config = {
        "ownership": src.get("ownership", "user_private"),
        "owner_user_id": src.get("owner_user_id"),
    }
    connector = TelegramConnector(source_id=src["source_id"], config=config, on_signal=lambda _: None)
    count = 0
    for ns in connector.parse(update):
        inbound = _to_inbound(ns)
        await forward_inbound(inbound)
        count += 1
    return count


_bot: Optional[TelegramBotRunner] = None


def get_telegram_bot() -> Optional[TelegramBotRunner]:
    return _bot


async def register_telegram_webhook() -> None:
    """启动时向 Telegram 注册 webhook（TELEGRAM_USE_WEBHOOK=true）。"""
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_USE_WEBHOOK:
        return
    url = settings.TELEGRAM_WEBHOOK_URL.strip()
    if not url:
        logger.warning("TELEGRAM_USE_WEBHOOK=true 但未设置 TELEGRAM_WEBHOOK_URL")
        return
    payload: Dict[str, Any] = {"url": url, "drop_pending_updates": True}
    if settings.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = settings.TELEGRAM_WEBHOOK_SECRET
    api_url = f"{API_BASE}/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=15.0) as client:
            resp = await client.post(api_url, json=payload)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            logger.warning("Telegram setWebhook failed: %s", data.get("description", "unknown"))
            return
        logger.info("Telegram setWebhook 成功: %s", url)
    except Exception as e:  # noqa: BLE001
        logger.warning("Telegram setWebhook 错误（ingest 仍启动）: %s", e)


async def start_telegram_bot() -> None:
    global _bot
    if _bot is not None:
        return
    _bot = TelegramBotRunner()
    await _bot._refresh_sources()
    if settings.TELEGRAM_USE_WEBHOOK:
        await register_telegram_webhook()
        logger.info("Telegram webhook 模式，跳过 long-polling")
        return
    asyncio.create_task(_bot.run())


async def stop_telegram_bot() -> None:
    global _bot
    if _bot:
        _bot.stop()
        _bot = None
