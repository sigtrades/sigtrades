"""Webhook BaseSignalSource 实现。"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List

from sigtrades_core.signal.models import Signal
from sigtrades_core.sources.base import BaseSignalSource, NormalizedSignal, Ownership


class WebhookConnector(BaseSignalSource):
    kind = "webhook"

    @property
    def ownership(self) -> Ownership:
        own = (self.config.get("ownership") or "user_private").lower()
        return Ownership.PLATFORM_SHARED if own == "platform_shared" else Ownership.USER_PRIVATE

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def parse(self, raw: Any) -> List[NormalizedSignal]:
        payload = raw if isinstance(raw, dict) else {"raw_text": str(raw)}
        signal_id = payload.get("signal_id") or f"wh-{uuid.uuid4().hex[:12]}"
        signal = Signal(
            signal_id=signal_id,
            timestamp=payload.get("timestamp", time.time()),
            action=(payload.get("action") or payload.get("side") or "").upper(),
            symbol=payload.get("symbol") or payload.get("ticker") or "",
            quantity=int(payload.get("quantity") or payload.get("contracts") or 0),
            order_type=payload.get("order_type", "MKT"),
            limit_price=payload.get("limit_price") or payload.get("price"),
            metadata={"raw": payload},
        )
        return [NormalizedSignal(
            signal=signal,
            source_id=self.source_id,
            ownership=self.ownership,
            owner_user_id=self.config.get("owner_user_id"),
            raw=payload,
        )]
