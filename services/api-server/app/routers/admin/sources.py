"""管理员 — 信号源 CRUD + Discord 审核清单。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import SignalSource, User
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext

router = APIRouter()


class SourceUpsert(BaseModel):
    source_id: str
    kind: str = "discord"
    ownership: str = "platform_shared"
    name: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


def _source_dict(s: SignalSource, owner_email: str | None = None) -> dict:
    cfg = s.config or {}
    return {
        "source_id": s.source_id,
        "kind": s.kind,
        "ownership": s.ownership,
        "owner_user_id": str(s.owner_user_id) if s.owner_user_id else None,
        "owner_email": owner_email,
        "discord_username": cfg.get("discord_username") or None,
        "name": s.name,
        "is_active": s.is_active,
        "config": s.config,
    }


@router.get("")
async def admin_sources(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(
            select(SignalSource, User.email)
            .outerjoin(User, User.id == SignalSource.owner_user_id)
            .order_by(SignalSource.source_id)
        )
    ).all()
    return {
        "success": True,
        "data": [_source_dict(s, email) for s, email in rows],
    }


@router.post("")
async def create_source(
    req: SourceUpsert,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.execute(select(SignalSource).where(SignalSource.source_id == req.source_id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="source_id exists")
    db.add(
        SignalSource(
            source_id=req.source_id,
            kind=req.kind,
            ownership=req.ownership,
            name=req.name,
            config=req.config,
            is_active=req.is_active,
        )
    )
    await db.commit()
    return {"success": True}


@router.put("/{source_id}")
async def update_source(
    source_id: str,
    req: SourceUpsert,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SignalSource).where(SignalSource.source_id == source_id))
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="not found")
    src.kind = req.kind
    src.ownership = req.ownership
    src.name = req.name
    src.config = req.config
    src.is_active = req.is_active
    await db.commit()
    return {"success": True}


@router.delete("/{source_id}")
async def delete_source(
    source_id: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(SignalSource).where(SignalSource.source_id == source_id))
    src = result.scalar_one_or_none()
    if not src:
        raise HTTPException(status_code=404, detail="not found")
    src.is_active = False
    await db.commit()
    return {"success": True}


discord_router = APIRouter()


@discord_router.get("/bot-audit")
async def discord_bot_audit(_: bool = Depends(verify_admin_token)):
    return {
        "success": True,
        "data": {
            "checklist": [
                "Bot Token 配置于 DISCORD_BOT_TOKEN",
                "Application ID 配置于 DISCORD_APPLICATION_ID",
                "Developer Portal → Bot → Privileged Gateway Intents: Message Content Intent ON",
                "100+ 服务器需提交 Discord 审核说明：只读信号频道、不做 selfbot、用户授权 bot",
                "隐私政策 URL + 服务条款链接",
                "Bot 邀请权限：View Channels + Read Message History + Send Messages（可选）",
            ],
            "invite_template": "https://discord.com/api/oauth2/authorize?client_id={APP_ID}&permissions={PERMS}&scope=bot%20applications.commands",
        },
    }
