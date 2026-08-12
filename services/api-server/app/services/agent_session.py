"""Agent 登录会话：单设备在线，新登录挤掉旧 token / 旧连接。"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AgentToken, User
from app.security import generate_agent_token, hash_agent_token
from app.services.entitlements import has_feature

logger = logging.getLogger(__name__)

MAX_AGENT_TOKENS_MULTI = 5


async def max_agent_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    if await has_feature(db, user_id, "multi_agent"):
        return MAX_AGENT_TOKENS_MULTI
    return 1


async def count_active_tokens(db: AsyncSession, user_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(AgentToken)
        .where(AgentToken.user_id == user_id, AgentToken.revoked_at.is_(None))
    )
    return int(result.scalar() or 0)


async def revoke_user_agent_tokens(
    db: AsyncSession, user_id: uuid.UUID, *, except_id: Optional[uuid.UUID] = None
) -> None:
    now = datetime.now(timezone.utc)
    stmt = select(AgentToken).where(
        AgentToken.user_id == user_id,
        AgentToken.revoked_at.is_(None),
    )
    if except_id is not None:
        stmt = stmt.where(AgentToken.id != except_id)
    rows = (await db.execute(stmt)).scalars().all()
    for row in rows:
        row.revoked_at = now


async def disconnect_relay_agents(user_id: str) -> None:
    url = f"{settings.RELAY_GATEWAY_URL.rstrip('/')}/internal/disconnect-user/{user_id}"
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=3.0) as client:
            await client.post(url, headers={"X-Internal-Secret": settings.INTERNAL_SECRET})
    except Exception as e:  # noqa: BLE001
        logger.debug("relay disconnect skipped user=%s: %s", user_id, e)


async def issue_agent_token(
    db: AsyncSession,
    user: User,
    *,
    device_id: Optional[str],
    label: str,
    commit: bool = True,
) -> str:
    """签发新 Agent token，提升 session epoch，使旧 token 失效。"""
    limit = await max_agent_tokens(db, user.id)
    active = await count_active_tokens(db, user.id)
    if active >= limit:
        if limit <= 1:
            await revoke_user_agent_tokens(db, user.id)
        else:
            oldest = (
                await db.execute(
                    select(AgentToken)
                    .where(AgentToken.user_id == user.id, AgentToken.revoked_at.is_(None))
                    .order_by(AgentToken.created_at.asc())
                    .limit(active - limit + 1)
                )
            ).scalars().all()
            now = datetime.now(timezone.utc)
            for row in oldest:
                row.revoked_at = now

    user.agent_session_epoch = int(user.agent_session_epoch or 0) + 1
    if device_id:
        user.agent_active_device_id = device_id

    plain = generate_agent_token()
    db.add(
        AgentToken(
            user_id=user.id,
            token_hash=hash_agent_token(plain),
            label=label,
            device_id=device_id,
            session_epoch=user.agent_session_epoch,
        )
    )
    if commit:
        await db.commit()
        await disconnect_relay_agents(str(user.id))
    else:
        await db.flush()
    return plain


async def claim_agent_ws(db: AsyncSession, user_token: str, device_id: str) -> str:
    """校验 token 并登记当前 WS 设备（单账号单设备）。"""
    if not user_token or not device_id:
        raise HTTPException(status_code=401, detail="invalid agent token")

    token_hash = hash_agent_token(user_token)
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

    current_epoch = int(user.agent_session_epoch or 0)
    token_epoch = int(token.session_epoch or 0)
    if token_epoch != current_epoch:
        raise HTTPException(status_code=401, detail="agent token superseded")

    bound = (token.device_id or "").strip()
    if bound and bound != device_id:
        raise HTTPException(status_code=401, detail="agent token bound to another device")

    if not bound:
        token.device_id = device_id

    user.agent_active_device_id = device_id
    token.last_seen_at = datetime.now(timezone.utc)
    await db.commit()
    return str(user.id)
