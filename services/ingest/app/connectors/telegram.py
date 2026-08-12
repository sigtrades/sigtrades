"""Telegram Bot connector — 频道/群组文本消息（合规 bot，非 userbot）。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

from sigtrades_core.sources.base import BaseSignalSource, NormalizedSignal, Ownership


class TelegramConnector(BaseSignalSource):
    kind = "telegram"

    @property
    def ownership(self) -> Ownership:
        own = (self.config.get("ownership") or "user_private").lower()
        return Ownership.PLATFORM_SHARED if own == "platform_shared" else Ownership.USER_PRIVATE

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def parse(self, raw: Any) -> List[NormalizedSignal]:
        """解析 Telegram Bot API Update（message 或 channel_post）。"""
        if not isinstance(raw, dict):
            return []

        msg = raw.get("message") or raw.get("channel_post") or raw
        if not isinstance(msg, dict):
            return []

        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id", ""))
        text = (msg.get("text") or msg.get("caption") or "").strip()
        if not text:
            return []

        from_user = msg.get("from") or msg.get("sender_chat") or {}
        author = (
            from_user.get("username")
            or from_user.get("title")
            or " ".join(
                p for p in (from_user.get("first_name"), from_user.get("last_name")) if p
            ).strip()
            or None
        )

        signal_id = f"tg-{msg.get('message_id', uuid.uuid4().hex[:12])}"
        from sigtrades_core.signal.models import Signal

        signal = Signal(
            signal_id=signal_id,
            timestamp=msg.get("date", time.time()),
            action="",
            symbol="",
            quantity=0,
            order_type="MKT",
            metadata={
                "telegram_message_id": msg.get("message_id"),
                "chat_id": chat_id,
                "chat_title": chat.get("title") or chat.get("username"),
                "author": author,
                "raw_text": text,
                "parse_mode": "ai",
                "parse_pending": True,
            },
        )
        return [NormalizedSignal(
            signal=signal,
            source_id=self.source_id,
            ownership=self.ownership,
            owner_user_id=self.config.get("owner_user_id"),
            raw=msg,
            confidence=0.5,
        )]
