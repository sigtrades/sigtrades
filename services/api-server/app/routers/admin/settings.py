"""管理员 — 系统设置。"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import AdminSetting
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext

router = APIRouter()


class SettingUpsert(BaseModel):
    value: dict


@router.get("")
async def get_settings(_: bool = Depends(verify_admin_token)):
    return {
        "success": True,
        "data": {
            "email": {
                "provider": "resend",
                "from_email": settings.RESEND_FROM_EMAIL,
                "from_name": settings.RESEND_FROM_NAME,
                "configured": bool(settings.RESEND_API_KEY and settings.RESEND_FROM_EMAIL),
            },
            "stripe": {
                "secret_key_configured": bool(settings.STRIPE_SECRET_KEY),
                "webhook_configured": bool(settings.STRIPE_WEBHOOK_SECRET),
            },
            "frontend_url": settings.FRONTEND_URL,
            "redis_url_configured": bool(settings.REDIS_URL),
            "admin_username": settings.ADMIN_USERNAME,
            "operations_username": settings.OPERATIONS_USERNAME,
        },
    }


@router.get("/kv")
async def list_kv_settings(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(AdminSetting).order_by(AdminSetting.key))).scalars().all()
    return {"success": True, "data": [r.to_dict() for r in rows]}


@router.put("/kv/{key}")
async def upsert_kv_setting(
    key: str,
    body: SettingUpsert,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == key))).scalar_one_or_none()
    if row is None:
        row = AdminSetting(key=key, value=body.value)
        db.add(row)
    else:
        row.value = body.value
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return {"success": True, "data": row.to_dict()}
