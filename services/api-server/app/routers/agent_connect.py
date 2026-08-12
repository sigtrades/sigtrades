"""Relay Agent 浏览器登录（网页授权 + Agent 轮询领取）。"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.deps import get_verified_user
from app.models import AgentConnectSession, AgentToken, User
from app.security import (
    create_state_token,
    decode_state_token,
    generate_agent_token,
    hash_agent_token,
)
from app.services.agent_session import disconnect_relay_agents, issue_agent_token
from app.services.crypto import decrypt, encrypt

router = APIRouter(tags=["agent-connect"])

SESSION_TTL_MINUTES = 15


class AgentConnectSessionRequest(BaseModel):
    device_id: str = Field(min_length=3, max_length=64)
    callback_port: Optional[int] = Field(default=None, ge=1024, le=65535)


class AgentConnectSessionResponse(BaseModel):
    state: str
    session_id: uuid.UUID
    poll_secret: str
    connect_url: str
    expires_in: int = 900


class AgentConnectInfoResponse(BaseModel):
    device_id: str
    relay_url: str


class AgentConnectAuthorizeRequest(BaseModel):
    state: str = Field(min_length=10)


class AgentConnectAuthorizeResponse(BaseModel):
    authorized: bool = True
    redirect_url: Optional[str] = None


class AgentConnectPollRequest(BaseModel):
    session_id: uuid.UUID
    poll_secret: str = Field(min_length=20, max_length=256)


class AgentConnectPollResponse(BaseModel):
    status: Literal["pending", "authorized"]
    token: Optional[str] = None
    relay_url: Optional[str] = None
    email: Optional[str] = None


def _session_id_from_state(state: str) -> uuid.UUID:
    payload = decode_state_token(state)
    if not payload or payload.get("kind") != "agent_connect":
        raise HTTPException(status_code=400, detail="invalid or expired state")
    try:
        return uuid.UUID(str(payload["session_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="invalid or expired state") from exc


def _is_expired(row: AgentConnectSession) -> bool:
    return row.expires_at <= datetime.now(timezone.utc)


@router.post("/public/agent-connect/session", response_model=AgentConnectSessionResponse)
async def create_agent_connect_session(
    req: AgentConnectSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Agent 发起登录，poll_secret 仅交给 Agent，不进入浏览器 URL。"""
    poll_secret = generate_agent_token()
    row = AgentConnectSession(
        device_id=req.device_id.strip(),
        poll_secret_hash=hash_agent_token(poll_secret),
        legacy_callback_port=req.callback_port,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES),
    )
    db.add(row)
    await db.flush()
    state = create_state_token(
        {
            "session_id": str(row.id),
            "kind": "agent_connect",
        },
        ttl_minutes=SESSION_TTL_MINUTES,
    )
    await db.commit()
    connect_url = f"{settings.FRONTEND_URL.rstrip('/')}/agent/connect?state={quote(state, safe='')}"
    return AgentConnectSessionResponse(
        state=state,
        session_id=row.id,
        poll_secret=poll_secret,
        connect_url=connect_url,
    )


@router.get("/agent-connect/info", response_model=AgentConnectInfoResponse)
async def agent_connect_info(
    state: str = Query(..., min_length=10),
    db: AsyncSession = Depends(get_db),
):
    """Web 授权页读取待连接设备信息（无需登录）。"""
    session_id = _session_id_from_state(state)
    row = await db.get(AgentConnectSession, session_id)
    if row is None or _is_expired(row) or row.status in {"claimed", "expired"}:
        raise HTTPException(status_code=400, detail="invalid or expired state")
    return AgentConnectInfoResponse(
        device_id=row.device_id,
        relay_url=settings.RELAY_AGENT_WS_URL,
    )


@router.post("/agent-connect/authorize", response_model=AgentConnectAuthorizeResponse)
async def authorize_agent_connect(
    req: AgentConnectAuthorizeRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """用户确认后签发 Agent token；新版 Agent 从 poll 端点一次性领取。"""
    session_id = _session_id_from_state(req.state)
    row = (
        await db.execute(
            select(AgentConnectSession)
            .where(AgentConnectSession.id == session_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None or _is_expired(row):
        raise HTTPException(status_code=400, detail="invalid or expired state")
    if row.status == "authorized":
        return AgentConnectAuthorizeResponse()
    if row.status != "pending":
        raise HTTPException(status_code=409, detail="agent connect session already used")

    plain = await issue_agent_token(
        db,
        user,
        device_id=row.device_id,
        label=f"agent:{row.device_id}",
        commit=False,
    )
    now = datetime.now(timezone.utc)
    row.user_id = user.id
    row.authorized_at = now

    redirect_url = None
    if row.legacy_callback_port is not None:
        row.status = "claimed"
        row.claimed_at = now
        q_token = quote(plain, safe="")
        q_relay = quote(settings.RELAY_AGENT_WS_URL, safe="")
        redirect_url = (
            f"http://127.0.0.1:{row.legacy_callback_port}/callback"
            f"?token={q_token}&relay_url={q_relay}"
        )
    else:
        row.status = "authorized"
        row.pending_token_encrypted = encrypt(plain)

    await db.commit()
    await disconnect_relay_agents(str(user.id))
    return AgentConnectAuthorizeResponse(redirect_url=redirect_url)


class AgentMeRequest(BaseModel):
    user_token: str = Field(min_length=20, max_length=512)


class AgentMeResponse(BaseModel):
    email: str
    display_name: Optional[str] = None


@router.post("/public/agent/me", response_model=AgentMeResponse)
async def agent_me(req: AgentMeRequest, db: AsyncSession = Depends(get_db)):
    """Agent 用 user_token 查询绑定的账号信息。"""
    token_hash = hash_agent_token(req.user_token.strip())
    row = (
        await db.execute(
            select(AgentToken, User)
            .join(User, User.id == AgentToken.user_id)
            .where(AgentToken.token_hash == token_hash)
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=401, detail="invalid agent token")
    token, user = row
    if token.revoked_at is not None:
        raise HTTPException(status_code=401, detail="agent token revoked")
    if int(token.session_epoch or 0) != int(user.agent_session_epoch or 0):
        raise HTTPException(status_code=401, detail="agent token superseded")
    return AgentMeResponse(email=user.email, display_name=user.display_name)


@router.post("/public/agent-connect/poll", response_model=AgentConnectPollResponse)
async def poll_agent_connect(
    req: AgentConnectPollRequest,
    db: AsyncSession = Depends(get_db),
):
    """Agent 持 poll_secret 轮询并一次性领取 token。"""
    row = (
        await db.execute(
            select(AgentConnectSession)
            .where(
                AgentConnectSession.id == req.session_id,
                AgentConnectSession.poll_secret_hash == hash_agent_token(req.poll_secret),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="agent connect session not found")
    if _is_expired(row):
        row.status = "expired"
        row.pending_token_encrypted = None
        await db.commit()
        raise HTTPException(status_code=410, detail="agent connect session expired")
    if row.status == "pending":
        return AgentConnectPollResponse(status="pending")
    if row.status != "authorized" or not row.pending_token_encrypted:
        raise HTTPException(status_code=410, detail="agent connect session already claimed")

    token = decrypt(row.pending_token_encrypted)
    row.pending_token_encrypted = None
    row.status = "claimed"
    row.claimed_at = datetime.now(timezone.utc)
    email = None
    if row.user_id:
        user = await db.get(User, row.user_id)
        email = user.email if user else None
    await db.commit()
    return AgentConnectPollResponse(
        status="authorized",
        token=token,
        relay_url=settings.RELAY_AGENT_WS_URL,
        email=email,
    )
