"""signal-router: 校验后信号的动作裁决与路由分叉入口。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException

from app.config import settings
from app.models import InboundSignal
from app.router import route_signal

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="sigtrades signal-router")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "signal-router"}


def _require_internal(secret: str | None):
    if secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="invalid internal secret")


@app.post("/signal")
async def ingest_signal(inbound: InboundSignal, x_internal_secret: str | None = Header(default=None)):
    """接收来自 ingest / 外部信号服务的归一化信号，裁决并路由。"""
    _require_internal(x_internal_secret)
    outcomes = await route_signal(inbound)
    return {
        "signal_id": inbound.signal_id,
        "source_id": inbound.source_id,
        "routed": len(outcomes),
        "outcomes": [o.model_dump() for o in outcomes],
    }
