"""Discord Bot Gateway 长连接（合规 bot，非 selfbot）。

支持多 Bot Token：用户自带 Bot（BYOB）+ 可选平台级 DISCORD_BOT_TOKEN 兜底。
频道过滤：从 api-server /internal/discord-sources 拉取 source 配置。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
import websockets

from app.config import settings
from app.connectors.discord import DiscordConnector, normalized_to_inbound
from app.core.forward import forward_inbound

logger = logging.getLogger("discord-bot")

GATEWAY_URL = "https://gateway.discord.gg/?v=10&encoding=json"
INTENT_GUILD_MESSAGES = 1 << 9
INTENT_MESSAGE_CONTENT = 1 << 15


def _resolve_token_groups(sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """按 bot token 分组 channel -> source 映射。"""
    groups: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for src in sources:
        token = (src.get("bot_token") or "").strip() or (settings.DISCORD_BOT_TOKEN or "").strip()
        if not token:
            continue
        channel_map = groups.setdefault(token, {})
        for ch in src.get("channel_ids") or []:
            channel_map[str(ch)] = src
    return groups


class DiscordTokenSession:
    def __init__(self, token: str, channel_map: Dict[str, Dict[str, Any]]) -> None:
        self.token = token
        self.channel_map = channel_map
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = 2.0
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.warning("Discord Gateway 断开 (token …%s): %s，%.0fs 后重连", self.token[-6:], e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    async def _connect_once(self) -> None:
        async with websockets.connect(GATEWAY_URL, max_size=2**20) as ws:
            heartbeat_interval: Optional[float] = None
            seq: Optional[int] = None

            async for raw in ws:
                if self._stop.is_set():
                    break
                payload = json.loads(raw)
                op = payload.get("op")
                t = payload.get("t")
                d = payload.get("d")
                seq = payload.get("s", seq)

                if op == 10:  # HELLO
                    heartbeat_interval = d["heartbeat_interval"] / 1000.0
                    asyncio.create_task(self._heartbeat(ws, heartbeat_interval, lambda: seq))
                    await ws.send(json.dumps({
                        "op": 2,
                        "d": {
                            "token": self.token,
                            "intents": INTENT_GUILD_MESSAGES | INTENT_MESSAGE_CONTENT,
                            "properties": {"os": "linux", "browser": "sigtrades", "device": "sigtrades"},
                        },
                    }))
                elif op == 0 and t == "MESSAGE_CREATE":
                    await self._on_message(d)
                elif op in (7, 9):  # RECONNECT / INVALID SESSION
                    break

    async def _heartbeat(self, ws, interval: float, seq_fn) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            await ws.send(json.dumps({"op": 1, "d": seq_fn()}))

    async def _on_message(self, data: Dict[str, Any]) -> None:
        channel_id = str(data.get("channel_id", ""))
        src = self.channel_map.get(channel_id)
        if not src:
            return

        config = {
            "ownership": src.get("ownership", "user_private"),
            "owner_user_id": src.get("owner_user_id"),
        }
        connector = DiscordConnector(source_id=src["source_id"], config=config, on_signal=lambda _: None)
        event = {"t": "MESSAGE_CREATE", "d": data}
        for ns in connector.parse(event):
            inbound = normalized_to_inbound(ns)
            await forward_inbound(inbound)


class DiscordBotManager:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._sessions: Dict[str, asyncio.Task] = {}
        self._session_objs: Dict[str, DiscordTokenSession] = {}

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sync_sessions()
            except Exception as e:  # noqa: BLE001
                logger.warning("Discord manager sync failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
        for session in self._session_objs.values():
            session.stop()
        for task in self._sessions.values():
            task.cancel()
        self._sessions.clear()
        self._session_objs.clear()

    async def _fetch_sources(self) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            resp = await client.get(
                f"{settings.API_SERVER_URL}/internal/discord-sources",
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        resp.raise_for_status()
        return resp.json().get("sources", [])

    async def _sync_sessions(self) -> None:
        sources = await self._fetch_sources()
        groups = _resolve_token_groups(sources)
        active_tokens = set(groups.keys())

        for token in list(self._sessions.keys()):
            if token not in active_tokens:
                self._session_objs[token].stop()
                self._sessions[token].cancel()
                del self._sessions[token]
                del self._session_objs[token]
                logger.info("Discord session stopped (token …%s)", token[-6:])

        for token, channel_map in groups.items():
            existing = self._session_objs.get(token)
            if existing and existing.channel_map == channel_map and token in self._sessions:
                continue
            if existing:
                existing.stop()
                self._sessions[token].cancel()

            session = DiscordTokenSession(token, channel_map)
            self._session_objs[token] = session
            self._sessions[token] = asyncio.create_task(session.run())
            logger.info(
                "Discord session started (token …%s): %d channels",
                token[-6:],
                len(channel_map),
            )

        if not groups:
            logger.debug("Discord: no active sources with bot token")


_manager: Optional[DiscordBotManager] = None


async def start_discord_bot() -> None:
    global _manager
    if _manager is not None:
        return
    _manager = DiscordBotManager()
    asyncio.create_task(_manager.run())
    logger.info("Discord bot manager started")


async def stop_discord_bot() -> None:
    global _manager
    if _manager:
        _manager.stop()
        _manager = None
