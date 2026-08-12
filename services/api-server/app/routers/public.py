"""公开 API（无需认证）。"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.services.agent_release_service import (
    load_agent_releases,
    load_release_history,
    normalize_platform,
    platform_public_payload,
    public_history_item,
)
from app.services.confirm_trade_service import execute_action, peek_action
from app.services.risk_disclosure import (
    RISK_DISCLOSURE_VERSION,
    load_risk_disclosure_markdown,
)

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/risk-disclosure")
async def public_risk_disclosure():
    """公开风险揭示书正文（无需登录，供法律页展示）。"""
    try:
        markdown = load_risk_disclosure_markdown()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail="risk disclosure document missing") from exc
    return {
        "version": RISK_DISCLOSURE_VERSION,
        "markdown": markdown,
        "updated": "2026-07-31",
    }


def _compute_sha256_from_url(url: str) -> str:
    """若本地有对应文件则计算 sha256（可选）。"""
    if not url.startswith("file://"):
        return ""
    path = Path(url.replace("file://", ""))
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@router.get("/agent-version")
async def agent_version(
    platform: Optional[str] = Query(None, description="macos | windows"),
    db: AsyncSession = Depends(get_db),
):
    releases = await load_agent_releases(db)
    plat = normalize_platform(platform)

    if plat:
        data = releases[plat]
        payload = platform_public_payload(plat, data)
        if not payload["sha256"] and payload["download_url"].startswith("file://"):
            payload["sha256"] = _compute_sha256_from_url(payload["download_url"])
        return payload

    macos = platform_public_payload("macos", releases["macos"])
    windows = platform_public_payload("windows", releases["windows"])
    if not macos["sha256"] and macos["download_url"].startswith("file://"):
        macos["sha256"] = _compute_sha256_from_url(macos["download_url"])
    if not windows["sha256"] and windows["download_url"].startswith("file://"):
        windows["sha256"] = _compute_sha256_from_url(windows["download_url"])

    # 向后兼容：顶层字段默认 macOS
    return {
        **macos,
        "platforms": {
            "macos": macos,
            "windows": windows,
        },
    }


@router.get("/agent-releases/history")
async def agent_release_history(
    platform: Optional[str] = Query(None, description="macos | windows"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """公开：Agent 历史安装包列表（发布时已归档，可下载旧版本）。"""
    plat = normalize_platform(platform) if platform else None
    items = await load_release_history(db, platform=plat, limit=limit)
    return {
        "items": [public_history_item(i) for i in items],
        "total": len(items),
    }


@router.get("/firebase-config")
async def firebase_config():
    """Firebase Web 推送公开配置（供前端 / Service Worker 使用）。"""
    return {
        "apiKey": settings.FIREBASE_WEB_API_KEY,
        "authDomain": settings.FIREBASE_AUTH_DOMAIN,
        "projectId": settings.FCM_PROJECT_ID,
        "messagingSenderId": settings.FIREBASE_MESSAGING_SENDER_ID,
        "appId": settings.FIREBASE_WEB_APP_ID,
        "vapidKey": settings.FIREBASE_VAPID_KEY,
    }


class ConfirmTradeBody(BaseModel):
    token: str = Field(..., min_length=8)


@router.get("/confirm-trade")
async def confirm_trade_peek(
    token: str = Query(..., min_length=8),
    db: AsyncSession = Depends(get_db),
):
    """邮件落地页预览：不改状态，防安全扫描预取误下单。"""
    return await peek_action(db, token)


@router.post("/confirm-trade")
async def confirm_trade_execute(
    body: ConfirmTradeBody,
    db: AsyncSession = Depends(get_db),
):
    """落地页二次点击后真正确认/取消。"""
    return await execute_action(db, body.token)
