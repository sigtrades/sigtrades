"""relay-gateway: Agent 反向 WS hub + 内部下发 API。

- `WS /agent/ws`        : Agent 反向长连接（注册/心跳/状态/回执）
- `POST /internal/dispatch` : cloud-core/signal-router 把已裁决信号下发给某用户的 Agent
- `GET  /internal/agents/{user_id}` : 查询用户 Agent 在线状态/券商连通性
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sigtrades_protocol import (
    MessageType,
    Ack,
    ExecuteSignal,
    CancelSignal,
    PauseAgent,
    ProbeAccount,
    ProbeAccountResult,
    decode_message,
    encode_message,
)

from app.auth import authenticate_agent
from app.config import settings
from app.manager import AgentConnection, manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("relay-gateway")

# request_id -> Future[ProbeAccountResult]
_pending_probes: Dict[str, asyncio.Future] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_reap_stale_connections())
    yield
    task.cancel()
    for fut in list(_pending_probes.values()):
        if not fut.done():
            fut.cancel()
    _pending_probes.clear()


app = FastAPI(title="sigtrades relay-gateway", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "relay-gateway"}


# ----------------------------------------------------------------------
# Agent 反向 WS
# ----------------------------------------------------------------------
@app.websocket("/agent/ws")
async def agent_ws(ws: WebSocket):
    await ws.accept()
    conn: AgentConnection | None = None
    try:
        # 首帧必须是 agent_register
        raw = await ws.receive_text()
        msg = decode_message(raw)
        if msg.type != MessageType.AGENT_REGISTER:
            await ws.send_text(encode_message(Ack(ref_type="register", ok=False, message="首帧需为 agent_register")))
            await ws.close()
            return

        user_id = await authenticate_agent(msg.user_token, msg.device_id)
        if not user_id:
            await ws.send_text(encode_message(Ack(ref_type="register", ok=False, message="认证失败")))
            await ws.close()
            return

        conn = AgentConnection(
            user_id=user_id,
            device_id=msg.device_id,
            ws=ws,
            capabilities=msg.capabilities,
            platform=msg.platform,
            agent_version=msg.agent_version,
        )
        displaced = await manager.register(conn)
        for old in displaced:
            try:
                await old.ws.send_text(
                    encode_message(Ack(ref_type="register", ok=False, message="session_displaced"))
                )
                await old.ws.close()
            except Exception:  # noqa: BLE001
                pass

        await ws.send_text(encode_message(Ack(ref_type="register", ok=True, message="registered")))
        await _notify_presence(user_id)

        # 消息循环
        while True:
            raw = await ws.receive_text()
            await _handle_upstream(conn, raw)

    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("WS 异常: %s", e)
    finally:
        if conn is not None:
            # 必须带 conn：同 device 重连后，旧 socket 收尾不能删掉新登记
            manager.remove(conn.user_id, conn.device_id, conn=conn)
            await _notify_presence(conn.user_id)


async def _handle_upstream(conn: AgentConnection, raw: str):
    try:
        msg = decode_message(raw)
    except Exception as e:  # noqa: BLE001
        logger.warning("无法解析上行消息: %s", e)
        return

    if msg.type == MessageType.AGENT_HEARTBEAT:
        manager.touch(conn.user_id, conn.device_id)
    elif msg.type == MessageType.AGENT_STATUS:
        conn.brokers = msg.brokers
        conn.gateways = list(getattr(msg, "gateways", None) or [])
        await _notify_presence(conn.user_id)
    elif msg.type == MessageType.EXECUTION_REPORT:
        await _forward_report(msg, conn.user_id)
    elif msg.type == MessageType.PROBE_ACCOUNT_RESULT:
        fut = _pending_probes.get(msg.request_id)
        if fut is not None and not fut.done():
            fut.set_result(msg)
    else:
        logger.info("忽略上行类型: %s", msg.type)


async def _forward_report(report, user_id: str) -> None:
    """把执行回执转发给 api-server 落库。"""
    try:
        payload = report.model_dump()
        payload["user_id"] = user_id
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(
                settings.REPORT_SINK_URL,
                json=payload,
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
    except Exception as e:  # noqa: BLE001
        logger.error("转发执行回执失败: %s", e)


async def _notify_presence(user_id: str) -> None:
    """把用户 Agent 在线/券商连通性同步给 api-server（供前端展示）。

    仅同步 presence，不上线发邮件（省配额；连接状态看控制台即可）。
    """
    online = bool(manager.list_user(user_id))
    payload = {
        "user_id": user_id,
        "online": online,
        "brokers": manager.online_brokers(user_id),
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
            await client.post(
                f"{settings.API_SERVER_URL}/internal/agent-presence",
                json=payload,
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------------
# 内部下发 API
# ----------------------------------------------------------------------
def _require_internal(secret: str | None):
    if secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="invalid internal secret")


class DispatchRequest(BaseModel):
    user_id: str
    execute: ExecuteSignal
    device_id: str | None = None


@app.post("/internal/dispatch")
async def dispatch(req: DispatchRequest, x_internal_secret: str | None = Header(default=None)):
    """把已裁决信号下发到用户对应券商的在线 Agent。Agent 离线返回 offline。"""
    _require_internal(x_internal_secret)
    conn = manager.find_for_broker(req.user_id, req.execute.broker, req.device_id)
    if conn is None:
        return {"delivered": False, "reason": "agent_offline", "broker": req.execute.broker}
    try:
        await conn.ws.send_text(encode_message(req.execute))
    except Exception as e:  # noqa: BLE001
        manager.remove(conn.user_id, conn.device_id)
        return {"delivered": False, "reason": "send_failed", "error": str(e)}
    return {"delivered": True, "device_id": conn.device_id}


class CancelRequest(BaseModel):
    user_id: str
    cancel: CancelSignal
    broker: str
    device_id: str | None = None


@app.post("/internal/cancel")
async def cancel(req: CancelRequest, x_internal_secret: str | None = Header(default=None)):
    _require_internal(x_internal_secret)
    conn = manager.find_for_broker(req.user_id, req.broker, req.device_id)
    if conn is None:
        return {"delivered": False, "reason": "agent_offline"}
    await conn.ws.send_text(encode_message(req.cancel))
    return {"delivered": True}


class PauseRequest(BaseModel):
    user_id: str
    paused: bool = True
    reason: str | None = None


@app.post("/internal/pause")
async def pause(req: PauseRequest, x_internal_secret: str | None = Header(default=None)):
    """全局急停：暂停/恢复用户所有 Agent 的自动交易。"""
    _require_internal(x_internal_secret)
    msg = PauseAgent(paused=req.paused, reason=req.reason)
    affected = 0
    for conn in manager.list_user(req.user_id):
        conn.paused = req.paused
        try:
            await conn.ws.send_text(encode_message(msg))
            affected += 1
        except Exception:  # noqa: BLE001
            pass
    return {"affected": affected, "paused": req.paused}


@app.get("/internal/agents/{user_id}")
async def agents(user_id: str, x_internal_secret: str | None = Header(default=None)):
    _require_internal(x_internal_secret)
    return {
        "user_id": user_id,
        "online": bool(manager.list_user(user_id)),
        "devices": [
            {
                "device_id": c.device_id,
                "platform": c.platform,
                "version": c.agent_version,
                "capabilities": c.capabilities,
                "brokers": c.brokers,
                "gateways": c.gateways,
                "paused": c.paused,
            }
            for c in manager.list_user(user_id)
        ],
        "brokers": manager.online_brokers(user_id),
    }


class ProbeAgentAccountRequest(BaseModel):
    user_id: str
    broker: str
    account_id: str | None = None
    device_id: str | None = None


@app.post("/internal/probe-account")
async def probe_agent_account(
    req: ProbeAgentAccountRequest,
    x_internal_secret: str | None = Header(default=None),
):
    """请求在线 Agent 探测本地 IBKR/富途账户。"""
    _require_internal(x_internal_secret)
    conn = manager.find_for_broker(req.user_id, req.broker, req.device_id)
    if conn is None:
        return {
            "ok": False,
            "broker": req.broker,
            "account_id": req.account_id,
            "account_summary": None,
            "error": "agent_offline",
            "device_id": None,
        }

    request_id = uuid.uuid4().hex
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    _pending_probes[request_id] = fut
    try:
        await conn.ws.send_text(
            encode_message(
                ProbeAccount(
                    request_id=request_id,
                    broker=req.broker,
                    account_id=req.account_id,
                )
            )
        )
        result: ProbeAccountResult = await asyncio.wait_for(fut, timeout=25.0)
        return {
            "ok": bool(result.ok),
            "broker": result.broker or req.broker,
            "account_id": result.account_id or req.account_id,
            "account_summary": result.account_summary,
            "error": result.error,
            "device_id": result.device_id or conn.device_id,
        }
    except asyncio.TimeoutError:
        return {
            "ok": False,
            "broker": req.broker,
            "account_id": req.account_id,
            "account_summary": None,
            "error": "probe_timeout",
            "device_id": conn.device_id,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "broker": req.broker,
            "account_id": req.account_id,
            "account_summary": None,
            "error": str(e),
            "device_id": conn.device_id,
        }
    finally:
        _pending_probes.pop(request_id, None)


@app.post("/internal/disconnect-user/{user_id}")
async def disconnect_user(user_id: str, x_internal_secret: str | None = Header(default=None)):
    """强制断开某用户所有 Agent WS（新设备登录挤掉旧连接）。"""
    _require_internal(x_internal_secret)
    displaced = manager.disconnect_user(user_id)
    for conn in displaced:
        try:
            await conn.ws.send_text(
                encode_message(Ack(ref_type="register", ok=False, message="session_displaced"))
            )
            await conn.ws.close()
        except Exception:  # noqa: BLE001
            pass
    await _notify_presence(user_id)
    return {"disconnected": len(displaced)}


# ----------------------------------------------------------------------
# 后台：清理心跳超时连接
# ----------------------------------------------------------------------
async def _reap_stale_connections():
    import time

    while True:
        await asyncio.sleep(settings.HEARTBEAT_TIMEOUT / 2)
        now = time.time()
        stale = []
        for user_id, devices in list(manager._conns.items()):
            for device_id, conn in list(devices.items()):
                if now - conn.last_heartbeat > settings.HEARTBEAT_TIMEOUT:
                    stale.append((user_id, device_id, conn))
        for user_id, device_id, conn in stale:
            logger.info("心跳超时，断开 user=%s device=%s", user_id, device_id)
            try:
                await conn.ws.close()
            except Exception:  # noqa: BLE001
                pass
            manager.remove(user_id, device_id)
            await _notify_presence(user_id)
