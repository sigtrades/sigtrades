"""管理员 — Agent 发布版本（macOS / Windows）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.routers.admin.deps import require_admin_only, verify_admin_token
from app.services.admin_auth import AdminContext
from app.services.agent_release_service import (
    PLATFORMS,
    bump_patch_version,
    delete_release_history,
    load_agent_releases,
    load_release_history,
    normalize_platform,
    publish_agent_release,
    restore_release_history,
    save_agent_releases,
    scan_local_agent_packages,
)

router = APIRouter()


class PlatformRelease(BaseModel):
    latest_version: str = ""
    min_version: str = ""
    download_url: str = ""
    sha256: str = ""
    release_notes: str = ""


class AgentReleasesBody(BaseModel):
    macos: Optional[PlatformRelease] = None
    windows: Optional[PlatformRelease] = None


class PublishBody(BaseModel):
    platform: str
    release: PlatformRelease


@router.get("/releases")
async def get_agent_releases_admin(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    data = await load_agent_releases(db)
    history = await load_release_history(db, limit=20)
    return {
        "success": True,
        "data": {
            "platforms": data,
            "recent_history": history,
            "env_fallback": {
                "macos": "AGENT_LATEST_VERSION / AGENT_DOWNLOAD_URL / AGENT_SHA256",
                "windows": "AGENT_WINDOWS_* 或回退 macOS 版本号",
            },
        },
    }


@router.get("/releases/local-packages")
async def get_local_agent_packages(
    _: bool = Depends(verify_admin_token),
):
    """扫描 data/agent-releases/，供后台一键填入下载地址与 SHA256。"""
    return {"success": True, "data": scan_local_agent_packages()}


class BumpVersionBody(BaseModel):
    version: str = ""


@router.post("/releases/bump-version")
async def bump_agent_release_version(
    body: BumpVersionBody,
    _: bool = Depends(verify_admin_token),
):
    next_ver = bump_patch_version(body.version)
    return {"success": True, "data": {"version": next_ver, "from": (body.version or "").strip()}}


@router.get("/releases/history")
async def get_agent_release_history(
    platform: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    plat = normalize_platform(platform) if platform else None
    items = await load_release_history(db, platform=plat, limit=limit)
    return {"success": True, "data": {"items": items, "total": len(items)}}


@router.put("/releases")
async def put_agent_releases_admin(
    body: AgentReleasesBody,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    payload: Dict[str, Dict[str, Any]] = {}
    if body.macos is not None:
        payload["macos"] = body.macos.model_dump()
    if body.windows is not None:
        payload["windows"] = body.windows.model_dump()
    if not payload:
        raise HTTPException(status_code=400, detail="至少提供一个平台配置")
    data = await save_agent_releases(db, payload)
    return {"success": True, "data": {"platforms": data}}


@router.post("/releases/publish")
async def publish_agent_release_admin(
    body: PublishBody,
    ctx: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    plat = normalize_platform(body.platform)
    if plat not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform 须为 macos 或 windows")
    if not body.release.latest_version.strip():
        raise HTTPException(status_code=400, detail="请填写版本号")
    try:
        entry = await publish_agent_release(
            db,
            plat,
            body.release.model_dump(),
            published_by=ctx.username,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    platforms = await load_agent_releases(db)
    return {"success": True, "data": {"entry": entry, "platforms": platforms}}


@router.post("/releases/history/{entry_id}/restore")
async def restore_agent_release_history(
    entry_id: str,
    ctx: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        entry = await restore_release_history(db, entry_id, published_by=ctx.username)
    except LookupError:
        raise HTTPException(status_code=404, detail="历史记录不存在") from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    platforms = await load_agent_releases(db)
    return {"success": True, "data": {"entry": entry, "platforms": platforms}}


@router.delete("/releases/history/{entry_id}")
async def delete_agent_release_history(
    entry_id: str,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await delete_release_history(db, entry_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="历史记录不存在") from None
    return {"success": True, "data": result}


@router.put("/releases/{platform}")
async def put_agent_release_platform(
    platform: str,
    body: PlatformRelease,
    _: AdminContext = Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    plat = normalize_platform(platform)
    if plat not in PLATFORMS:
        raise HTTPException(status_code=400, detail="platform 须为 macos 或 windows")
    data = await save_agent_releases(db, {plat: body.model_dump()})
    return {"success": True, "data": {"platform": plat, "release": data[plat]}}
