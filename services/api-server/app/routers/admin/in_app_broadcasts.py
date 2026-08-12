"""管理员 — 全站公告。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import InAppBroadcast
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext
from app.services.in_app_broadcast_service import (
    VALID_EMAIL_AUDIENCES,
    count_email_recipients,
    do_broadcast,
)

router = APIRouter()

_EMAIL_AUDIENCE = Literal["none", "all", "members"]


class InAppBroadcastCreate(BaseModel):
    title_zh: str = Field(default="", max_length=200)
    title_en: str = Field(default="", max_length=200)
    body_md_zh: str = ""
    body_md_en: str = ""
    email_audience: _EMAIL_AUDIENCE = "none"


class InAppBroadcastUpdate(BaseModel):
    title_zh: Optional[str] = Field(default=None, max_length=200)
    title_en: Optional[str] = Field(default=None, max_length=200)
    body_md_zh: Optional[str] = None
    body_md_en: Optional[str] = None
    email_audience: Optional[_EMAIL_AUDIENCE] = None


@router.get("")
async def list_in_app_broadcasts(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    rows = (
        await db.execute(select(InAppBroadcast).order_by(InAppBroadcast.created_at.desc()))
    ).scalars().all()
    return {"success": True, "data": [r.to_dict() for r in rows]}


@router.post("")
async def create_in_app_broadcast(
    body: InAppBroadcastCreate,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = InAppBroadcast(
        title_zh=body.title_zh,
        title_en=body.title_en,
        body_md_zh=body.body_md_zh,
        body_md_en=body.body_md_en,
        email_audience=body.email_audience,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": row.to_dict()}


@router.get("/{bid}")
async def get_in_app_broadcast(
    bid: UUID,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    return {"success": True, "data": row.to_dict()}


@router.put("/{bid}")
async def update_in_app_broadcast(
    bid: UUID,
    body: InAppBroadcastUpdate,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if row.revoked_at is not None:
        raise HTTPException(status_code=400, detail="已撤回，不能编辑；请新建一条。")
    if (row.send_count or 0) > 0:
        raise HTTPException(status_code=400, detail="已发送过，不能改文案；可补发或新建一条。")
    if body.title_zh is not None:
        row.title_zh = body.title_zh
    if body.title_en is not None:
        row.title_en = body.title_en
    if body.body_md_zh is not None:
        row.body_md_zh = body.body_md_zh
    if body.body_md_en is not None:
        row.body_md_en = body.body_md_en
    if body.email_audience is not None:
        row.email_audience = body.email_audience
    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": row.to_dict()}


@router.delete("/{bid}")
async def delete_in_app_broadcast(
    bid: UUID,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if (row.send_count or 0) > 0:
        raise HTTPException(status_code=400, detail="已发送过，不能删除；可改为撤回以隐藏用户端展示。")
    await db.execute(delete(InAppBroadcast).where(InAppBroadcast.id == bid))
    await db.commit()
    return {"success": True, "message": "已删除"}


@router.post("/{bid}/send")
async def send_first(
    bid: UUID,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if (row.send_count or 0) > 0:
        raise HTTPException(status_code=400, detail="已执行过首次发送，请用「补发」。")
    if row.revoked_at is not None:
        raise HTTPException(status_code=400, detail="已撤回，无法发送。")
    res = await do_broadcast(db, bid)
    if res.get("error") == "empty_config":
        raise HTTPException(status_code=400, detail=res.get("detail"))
    if res.get("error") == "revoked":
        raise HTTPException(status_code=400, detail=res.get("detail"))
    await db.commit()
    return {"success": True, "data": res}


@router.post("/{bid}/resend")
async def resend(
    bid: UUID,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if (row.send_count or 0) < 1:
        raise HTTPException(status_code=400, detail="请先使用「立即发送（首次）」。")
    if row.revoked_at is not None:
        raise HTTPException(status_code=400, detail="已撤回，不能补发；请新建一条。")
    res = await do_broadcast(db, bid)
    if res.get("error") == "empty_config":
        raise HTTPException(status_code=400, detail=res.get("detail"))
    if res.get("error") == "revoked":
        raise HTTPException(status_code=400, detail=res.get("detail"))
    await db.commit()
    return {"success": True, "data": res}


@router.post("/{bid}/revoke")
async def revoke(
    bid: UUID,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    if (row.send_count or 0) < 1:
        raise HTTPException(status_code=400, detail="尚未发出过，可直接删除，无需撤回。")
    if row.revoked_at is not None:
        raise HTTPException(status_code=400, detail="已撤回过。")
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": row.to_dict()}


@router.get("/{bid}/email-recipients")
async def email_recipients_estimate(
    bid: UUID,
    audience: Literal["all", "members"] = "all",
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    if audience not in VALID_EMAIL_AUDIENCES:
        raise HTTPException(status_code=400, detail="人群只能是 all 或 members")
    row = (await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == bid))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="记录不存在")
    estimated = await count_email_recipients(db, audience)
    return {"success": True, "data": {"audience": audience, "recipients_estimated": estimated}}
