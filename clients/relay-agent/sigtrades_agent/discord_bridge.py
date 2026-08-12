"""Discord 个人频道桥接：用户 Token + Gateway 监听 → POST sigtrades Webhook。"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set

import httpx
import websockets
from sigtrades_core.discord.message_text import extract_discord_message_text

from sigtrades_agent.discord_identity import (
    DISCORD_API_BASE,
    GATEWAY_URL,
    api_headers,
    gateway_identify_payload,
)

logger = logging.getLogger("discord-bridge")

TEXT_CHANNEL_TYPES = {0, 5, 10, 11, 12}  # GUILD_TEXT, ANNOUNCEMENT, threads


@dataclass
class TestMessage:
    channel_id: str
    channel_name: str
    message_id: str
    author: str
    content: str
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "message_id": self.message_id,
            "author": self.author,
            "content": self.content,
            "ts": self.ts,
        }


@dataclass
class DiscordBridgeState:
    token: str = ""
    channel_ids: List[str] = field(default_factory=list)
    channel_labels: Dict[str, str] = field(default_factory=dict)
    webhook_url: str = ""
    running: bool = False
    connected: bool = False
    last_error: str = ""
    test_messages: Deque[TestMessage] = field(default_factory=lambda: deque(maxlen=50))
    _seen_ids: Set[str] = field(default_factory=set)

    def status_dict(self) -> dict[str, Any]:
        return {
            "has_token": bool(self.token),
            "channel_ids": self.channel_ids,
            "channel_labels": self.channel_labels,
            "webhook_url": self.webhook_url,
            "running": self.running,
            "connected": self.connected,
            "last_error": self.last_error,
        }


class DiscordBridge:
    def __init__(self) -> None:
        self.state = DiscordBridgeState()
        self._stop = asyncio.Event()
        self._task: Optional[asyncio.Task] = None

    def set_token(self, token: str) -> None:
        self.state.token = token.strip()
        self.state.last_error = ""

    def configure(
        self,
        *,
        channel_ids: List[str],
        channel_labels: Optional[Dict[str, str]] = None,
        webhook_url: str = "",
    ) -> None:
        self.state.channel_ids = [str(c).strip() for c in channel_ids if str(c).strip()]
        if channel_labels:
            self.state.channel_labels = {str(k): v for k, v in channel_labels.items()}
        if webhook_url:
            self.state.webhook_url = webhook_url.strip()

    async def validate_token(self) -> dict[str, Any]:
        if not self.state.token:
            raise ValueError("missing discord token")
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/users/@me",
                headers=api_headers(self.state.token),
            )
        if resp.status_code == 401:
            raise ValueError("invalid or expired discord token")
        resp.raise_for_status()
        data = resp.json()
        return {"id": data.get("id"), "username": data.get("username"), "global_name": data.get("global_name")}

    async def fetch_guilds(self) -> List[dict[str, Any]]:
        if not self.state.token:
            raise ValueError("missing discord token")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/users/@me/guilds",
                headers=api_headers(self.state.token),
            )
        resp.raise_for_status()
        return [
            {"id": g["id"], "name": g.get("name", ""), "icon": g.get("icon")}
            for g in resp.json()
        ]

    async def fetch_guild_channels(self, guild_id: str) -> List[dict[str, Any]]:
        if not self.state.token:
            raise ValueError("missing discord token")
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{DISCORD_API_BASE}/guilds/{guild_id}/channels",
                headers=api_headers(self.state.token),
            )
        if resp.status_code == 403:
            raise ValueError("no access to this server")
        resp.raise_for_status()
        out = []
        for ch in resp.json():
            if ch.get("type") not in TEXT_CHANNEL_TYPES:
                continue
            out.append({
                "id": ch["id"],
                "name": ch.get("name", ""),
                "guild_id": guild_id,
                "type": ch.get("type"),
            })
        return sorted(out, key=lambda x: x["name"].lower())

    def get_test_messages(self, limit: int = 20) -> List[dict[str, Any]]:
        items = list(self.state.test_messages)[-limit:]
        return [m.to_dict() for m in reversed(items)]

    async def start(self) -> None:
        if not self.state.token:
            raise ValueError("missing discord token")
        if not self.state.channel_ids:
            raise ValueError("no channels selected")
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self.state.running = True
        self._task = asyncio.create_task(self._run_loop(), name="discord-bridge")

    async def stop(self) -> None:
        self._stop.set()
        self.state.running = False
        self.state.connected = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def _run_loop(self) -> None:
        backoff = 2.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                backoff = 2.0
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                self.state.connected = False
                self.state.last_error = str(e)
                logger.warning("Discord bridge disconnected: %s, retry in %.0fs", e, backoff)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    break
                except asyncio.TimeoutError:
                    pass
                backoff = min(60.0, backoff * 2)
        self.state.running = False
        self.state.connected = False

    async def _connect_once(self) -> None:
        channel_set = set(self.state.channel_ids)
        async with websockets.connect(GATEWAY_URL, max_size=2**20) as ws:
            heartbeat_interval: Optional[float] = None
            seq: Optional[int] = None
            identified = False

            async for raw in ws:
                if self._stop.is_set():
                    break
                payload = json.loads(raw)
                op = payload.get("op")
                t = payload.get("t")
                d = payload.get("d")
                seq = payload.get("s", seq)

                if op == 10:
                    heartbeat_interval = d["heartbeat_interval"] / 1000.0
                    asyncio.create_task(self._heartbeat(ws, heartbeat_interval, lambda: seq))
                    await ws.send(json.dumps(gateway_identify_payload(self.state.token)))
                elif op == 0 and t == "READY":
                    identified = True
                    self.state.connected = True
                    self.state.last_error = ""
                    logger.info("Discord bridge READY, watching %d channel(s)", len(channel_set))
                elif op == 0 and t == "MESSAGE_CREATE" and identified:
                    await self._on_message(d, channel_set)
                elif op in (7, 9):
                    break

    async def _heartbeat(self, ws, interval: float, seq_fn) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            await ws.send(json.dumps({"op": 1, "d": seq_fn()}))

    async def _on_message(self, data: dict[str, Any], channel_set: set[str]) -> None:
        channel_id = str(data.get("channel_id", ""))
        if channel_id not in channel_set:
            return
        message_id = str(data.get("id", ""))
        if message_id in self.state._seen_ids:
            return
        self.state._seen_ids.add(message_id)
        if len(self.state._seen_ids) > 5000:
            self.state._seen_ids = set(list(self.state._seen_ids)[-2000:])

        content = extract_discord_message_text(data)
        if not content:
            return
        author = data.get("author", {})
        author_name = author.get("global_name") or author.get("username") or "unknown"
        label = self.state.channel_labels.get(channel_id, channel_id)

        test_msg = TestMessage(
            channel_id=channel_id,
            channel_name=label,
            message_id=message_id,
            author=author_name,
            content=content,
            ts=time.time(),
        )
        self.state.test_messages.append(test_msg)

        if self.state.webhook_url:
            await self._forward_webhook(test_msg, data)

    async def _forward_webhook(self, test_msg: TestMessage, raw: dict[str, Any]) -> None:
        body = {
            "raw_text": test_msg.content,
            "metadata": {
                "discord_channel_id": test_msg.channel_id,
                "discord_message_id": test_msg.message_id,
                "discord_author": test_msg.author,
                "source": "discord_bridge",
            },
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.state.webhook_url, json=body)
            if resp.status_code >= 400:
                logger.warning("webhook POST %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:  # noqa: BLE001
            logger.warning("webhook forward failed: %s", e)
