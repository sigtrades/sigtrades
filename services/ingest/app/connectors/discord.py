"""Discord 连接器骨架（合规 bot 事件，不做 selfbot）。

实现 BaseSignalSource 接口；处理 MESSAGE_CREATE 自然语言信号，默认 MKT_only。
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from sigtrades_core.discord.message_text import extract_discord_message_text
from sigtrades_core.sources.base import BaseSignalSource, NormalizedSignal, Ownership

logger = logging.getLogger(__name__)


class DiscordConnector(BaseSignalSource):
    kind = "discord"

    @property
    def ownership(self) -> Ownership:
        own = (self.config.get("ownership") or "user_private").lower()
        if own == "platform_shared":
            return Ownership.PLATFORM_SHARED
        return Ownership.USER_PRIVATE

    def start(self) -> None:
        logger.info("Discord connector started for source=%s", self.source_id)

    def stop(self) -> None:
        logger.info("Discord connector stopped for source=%s", self.source_id)

    def parse(self, raw: Any) -> List[NormalizedSignal]:
        """解析 Discord Gateway 事件 payload（MESSAGE_CREATE）。"""
        if not isinstance(raw, dict):
            return []
        if raw.get("t") != "MESSAGE_CREATE" and raw.get("type") != 0:
            # Interaction ping 等忽略
            if "content" not in raw and "d" not in raw:
                return []

        data = raw.get("d", raw)
        content = extract_discord_message_text(data)
        if not content:
            return []

        signal_id = f"dc-{data.get('id', uuid.uuid4().hex[:12])}"
        signal_dict = {
            "signal_id": signal_id,
            "timestamp": time.time(),
            "type": "ORDER",
            "action": "",
            "symbol": "",
            "quantity": 0,
            "order_type": "MKT",
            "metadata": {
                "discord_message_id": data.get("id"),
                "channel_id": data.get("channel_id"),
                "guild_id": data.get("guild_id"),
                "author": (data.get("author") or {}).get("username"),
                "raw_text": content,
                "parse_mode": "ai",
            },
        }

        owner = self.config.get("owner_user_id")
        return [NormalizedSignal(
            signal=_dict_to_signal(signal_dict),
            source_id=self.source_id,
            ownership=self.ownership,
            owner_user_id=owner,
            raw=data,
            confidence=0.5,
        )]


def _dict_to_signal(d: dict):
    from sigtrades_core.signal.models import Signal
    return Signal(
        signal_id=d["signal_id"],
        timestamp=d["timestamp"],
        type=d.get("type", "ORDER"),
        action=d.get("action", ""),
        symbol=d.get("symbol", ""),
        quantity=d.get("quantity", 0),
        order_type=d.get("order_type", "MKT"),
        metadata=d.get("metadata"),
    )


def normalized_to_inbound(ns: NormalizedSignal) -> Dict[str, Any]:
    return {
        "source_id": ns.source_id,
        "signal_id": ns.signal.signal_id,
        "signal": ns.signal.to_dict(),
        "ownership": ns.ownership.value,
        "owner_user_id": ns.owner_user_id,
    }


def verify_discord_signature(body: bytes, signature: str, timestamp: str, public_key: str) -> bool:
    """Discord Interactions 签名校验（Ed25519）。"""
    if not public_key:
        return True
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError

        verify_key = VerifyKey(bytes.fromhex(public_key))
        message = timestamp.encode() + body
        verify_key.verify(message, bytes.fromhex(signature))
        return True
    except (BadSignatureError, ValueError, ImportError):
        return False
