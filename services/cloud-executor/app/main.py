"""cloud-executor: 云端券商（老虎 / 长桥）执行入口。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI, Header, HTTPException, Request

from app.config import settings
from app.executor import execute

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="sigtrades cloud-executor")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "cloud-executor"}


def _require_internal(secret: str | None):
    if secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="invalid internal secret")


@app.post("/internal/execute")
async def internal_execute(request: Request, x_internal_secret: str | None = Header(default=None)):
    """signal-router 下发的云端执行请求（broker=tiger 等 REST 券商）。"""
    _require_internal(x_internal_secret)
    payload = await request.json()
    loop = asyncio.get_running_loop()
    return await execute(payload, loop)


@app.post("/internal/probe-account")
async def internal_probe_account(
    request: Request,
    x_internal_secret: str | None = Header(default=None),
):
    """api-server「测试账户」：在本进程探测（已安装 tigeropen/longbridge 等 SDK）。"""
    _require_internal(x_internal_secret)
    payload = await request.json()
    broker = (payload.get("broker") or "").strip().lower()
    config = payload.get("config") or {}
    if not broker:
        raise HTTPException(status_code=400, detail="broker required")
    if not isinstance(config, dict):
        raise HTTPException(status_code=400, detail="config must be object")

    from sigtrades_core.brokers.account_probe import probe_broker_account

    loop = asyncio.get_running_loop()
    probe = await loop.run_in_executor(None, probe_broker_account, broker, config)
    return probe.to_dict()
