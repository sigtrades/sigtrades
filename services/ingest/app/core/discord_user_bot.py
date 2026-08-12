"""Discord 用户 Token Gateway（个人频道桥接，云端监听）。"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, List, Optional, Set

import httpx
import websockets

from app.config import settings
from sigtrades_core.discord.message_text import extract_discord_message_text

from app.connectors.discord import DiscordConnector, normalized_to_inbound
from app.core.discord_identity import GATEWAY_URL, gateway_identify_payload
from app.core.forward import forward_inbound

logger = logging.getLogger("discord-user-bot")

_preview_by_source: Dict[str, Deque[dict]] = {}
_test_sessions: Dict[str, "_TestSession"] = {}


@dataclass
class _TestSession:
    session_id: str
    channel_ids: Set[str]
    channel_labels: Dict[str, str]
    messages: Deque[dict] = field(default_factory=lambda: deque(maxlen=50))
    task: Optional[asyncio.Task] = None
    bridge: Optional["DiscordUserTokenSession"] = None


def get_preview_messages(source_id: str, limit: int = 20) -> List[dict]:
    buf = _preview_by_source.get(source_id)
    if not buf:
        return []
    return list(buf)[-limit:][::-1]


def get_test_messages(session_id: str, limit: int = 20) -> List[dict]:
    sess = _test_sessions.get(session_id)
    if not sess:
        return []
    return list(sess.messages)[-limit:][::-1]


def _resolve_user_groups(sources: List[Dict[str, Any]]) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
    """Group active sources by token; each channel may fan out to multiple monitors."""
    groups: Dict[str, Dict[str, List[Dict[str, Any]]]] = {}
    for src in sources:
        token = (src.get("user_token") or "").strip()
        if not token:
            continue
        channel_map = groups.setdefault(token, {})
        for ch in src.get("channel_ids") or []:
            channel_map.setdefault(str(ch), []).append(src)
    return groups


def _channel_map_signature(channel_map: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[str]]:
    return {ch: [s["source_id"] for s in srcs] for ch, srcs in sorted(channel_map.items())}


class DiscordUserTokenSession:
    def __init__(
        self,
        token: str,
        channel_map: Dict[str, List[Dict[str, Any]]],
        *,
        preview_only: bool = False,
        preview_sink: Optional[Deque[dict]] = None,
        channel_labels: Optional[Dict[str, str]] = None,
    ) -> None:
        self.token = token
        self.channel_map = channel_map
        self.preview_only = preview_only
        self.preview_sink = preview_sink
        self.channel_labels = channel_labels or {}
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
                logger.warning("Discord user gateway disconnected: %s, retry %.0fs", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(60.0, backoff * 2)

    async def _connect_once(self) -> None:
        channel_set = set(self.channel_map.keys())
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

                if op == 10:
                    heartbeat_interval = d["heartbeat_interval"] / 1000.0
                    asyncio.create_task(self._heartbeat(ws, heartbeat_interval, lambda: seq))
                    await ws.send(json.dumps(gateway_identify_payload(self.token)))
                elif op == 0 and t == "MESSAGE_CREATE":
                    await self._on_message(d, channel_set)
                elif op in (7, 9):
                    break

    async def _heartbeat(self, ws, interval: float, seq_fn) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(interval)
            await ws.send(json.dumps({"op": 1, "d": seq_fn()}))

    async def _on_message(self, data: Dict[str, Any], channel_set: set[str]) -> None:
        channel_id = str(data.get("channel_id", ""))
        if channel_id not in channel_set:
            return
        content = extract_discord_message_text(data)
        if not content:
            return

        author = data.get("author", {})
        author_name = author.get("global_name") or author.get("username") or "unknown"
        targets = self.channel_map.get(channel_id) or []
        if not targets:
            return

        if self.preview_sink is not None:
            label = self.channel_labels.get(channel_id, channel_id)
            self.preview_sink.append(
                {
                    "channel_id": channel_id,
                    "channel_name": label,
                    "message_id": str(data.get("id", "")),
                    "author": author_name,
                    "content": content,
                    "ts": time.time(),
                }
            )

        if self.preview_only:
            return

        event = {"t": "MESSAGE_CREATE", "d": data}
        for src in targets:
            source_id = src["source_id"]
            src_labels = src.get("channel_labels") or {}
            label = src_labels.get(channel_id) or self.channel_labels.get(channel_id, channel_id)
            # 仅内存临时缓冲，供解析配置取样；流水线展示以 DB 执行记录为准。
            _preview_by_source.setdefault(source_id, deque(maxlen=50)).append(
                {
                    "channel_id": channel_id,
                    "channel_name": label,
                    "message_id": str(data.get("id", "")),
                    "author": author_name,
                    "content": content,
                    "ts": time.time(),
                }
            )

            config = {
                "ownership": src.get("ownership", "user_private"),
                "owner_user_id": src.get("owner_user_id"),
            }
            connector = DiscordConnector(source_id=source_id, config=config, on_signal=lambda _: None)
            for ns in connector.parse(event):
                inbound = normalized_to_inbound(ns)
                sig = inbound.get("signal") or {}
                meta = dict(sig.get("metadata") or {})
                meta["channel_name"] = label
                meta["author"] = author_name
                sig["metadata"] = meta
                inbound["signal"] = sig
                await forward_inbound(inbound)


class DiscordUserBotManager:
    def __init__(self) -> None:
        self._stop = asyncio.Event()
        self._sessions: Dict[str, asyncio.Task] = {}
        self._session_objs: Dict[str, DiscordUserTokenSession] = {}

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._sync_sessions()
            except Exception as e:  # noqa: BLE001
                logger.warning("Discord user manager sync failed: %s", e)
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
                f"{settings.API_SERVER_URL}/internal/discord-user-sources",
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        resp.raise_for_status()
        return resp.json().get("sources", [])

    async def _sync_sessions(self) -> None:
        sources = await self._fetch_sources()
        groups = _resolve_user_groups(sources)
        active_tokens = set(groups.keys())

        for token in list(self._sessions.keys()):
            if token not in active_tokens:
                self._session_objs[token].stop()
                self._sessions[token].cancel()
                del self._sessions[token]
                del self._session_objs[token]

        for token, channel_map in groups.items():
            labels: Dict[str, str] = {}
            for src in sources:
                if (src.get("user_token") or "").strip() != token:
                    continue
                for cid, name in (src.get("channel_labels") or {}).items():
                    labels[str(cid)] = name

            existing = self._session_objs.get(token)
            if (
                existing
                and _channel_map_signature(existing.channel_map) == _channel_map_signature(channel_map)
                and token in self._sessions
            ):
                continue
            if existing:
                existing.stop()
                self._sessions[token].cancel()

            session = DiscordUserTokenSession(token, channel_map, channel_labels=labels)
            self._session_objs[token] = session
            self._sessions[token] = asyncio.create_task(session.run())
            logger.info("Discord user session started (…%s): %d channels", token[-6:], len(channel_map))


_manager: Optional[DiscordUserBotManager] = None


async def start_discord_user_bot() -> None:
    global _manager
    if _manager is not None:
        return
    _manager = DiscordUserBotManager()
    asyncio.create_task(_manager.run())
    logger.info("Discord user bot manager started")


async def stop_discord_user_bot() -> None:
    global _manager
    if _manager:
        _manager.stop()
        _manager = None


async def start_test_listen(
    user_token: str,
    channel_ids: List[str],
    channel_labels: Optional[Dict[str, str]] = None,
    *,
    ttl_sec: int = 600,
) -> str:
    session_id = f"test-{uuid.uuid4().hex[:10]}"
    labels = channel_labels or {}
    channel_map = {str(c): [{"source_id": f"preview-{c}"}] for c in channel_ids}
    sess = _TestSession(
        session_id=session_id,
        channel_ids=set(str(c) for c in channel_ids),
        channel_labels=labels,
    )
    bridge = DiscordUserTokenSession(
        user_token.strip(),
        channel_map,
        preview_only=True,
        preview_sink=sess.messages,
        channel_labels=labels,
    )
    sess.bridge = bridge
    sess.task = asyncio.create_task(bridge.run())
    _test_sessions[session_id] = sess

    async def _expire() -> None:
        await asyncio.sleep(ttl_sec)
        bridge.stop()
        if sess.task:
            sess.task.cancel()
        _test_sessions.pop(session_id, None)

    asyncio.create_task(_expire())
    return session_id


async def stop_test_listen(session_id: str) -> None:
    sess = _test_sessions.pop(session_id, None)
    if not sess:
        return
    if sess.bridge:
        sess.bridge.stop()
    if sess.task:
        sess.task.cancel()
