"""Agent 发布版本：KV 覆盖 + .env 默认值 + 发布历史。"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import unquote, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import AdminSetting
from app.utils.datetime import format_et

logger = logging.getLogger(__name__)

Platform = Literal["macos", "windows"]
PLATFORMS: tuple[Platform, ...] = ("macos", "windows")
KV_KEY = "agent_releases"
HISTORY_KV_KEY = "agent_release_history"
MAX_HISTORY = 200

# 无版本别名（打包脚本会同步写一份）；清单优先带版本号文件名
LOCAL_FILENAMES: Dict[Platform, str] = {
    "macos": "sigtrades-agent-macos.dmg",
    "windows": "sigtrades-agent-windows.zip",
}
# macOS 回退：旧包或仅打了 zip 时仍可加载
LOCAL_FILENAME_FALLBACKS: Dict[Platform, tuple[str, ...]] = {
    "macos": ("sigtrades-agent-macos.zip",),
    "windows": (),
}
# 带版本号包：sigtrades-agent-macos-v0.1.2.dmg
LOCAL_VERSIONED_GLOBS: Dict[Platform, str] = {
    "macos": "sigtrades-agent-macos-v*.dmg",
    "windows": "sigtrades-agent-windows-v*.zip",
}


def _platform_field() -> Dict[str, str]:
    return {
        "latest_version": "",
        "min_version": "",
        "download_url": "",
        "sha256": "",
        "release_notes": "",
    }


def _env_defaults() -> Dict[str, Dict[str, str]]:
    macos_url = settings.AGENT_DOWNLOAD_URL or ""
    windows_url = settings.AGENT_WINDOWS_DOWNLOAD_URL or ""
    base_ver = settings.AGENT_LATEST_VERSION or "0.1.0"
    windows_ver = settings.AGENT_WINDOWS_LATEST_VERSION or base_ver
    return {
        "macos": {
            "latest_version": base_ver,
            "min_version": base_ver,
            "download_url": macos_url,
            "sha256": settings.AGENT_SHA256 or "",
            "release_notes": "",
        },
        "windows": {
            "latest_version": windows_ver,
            "min_version": windows_ver,
            "download_url": windows_url,
            "sha256": settings.AGENT_WINDOWS_SHA256 or "",
            "release_notes": "",
        },
    }


def normalize_platform(raw: Optional[str]) -> Optional[Platform]:
    if not raw:
        return None
    v = raw.strip().lower()
    if v in ("macos", "darwin", "mac", "osx"):
        return "macos"
    if v in ("windows", "win32", "win"):
        return "windows"
    return None


def _merge_platform(defaults: Dict[str, str], overrides: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out = dict(defaults)
    if not overrides:
        return out
    for key in _platform_field():
        val = overrides.get(key)
        if val is not None and str(val).strip() != "":
            out[key] = str(val).strip()
    if not out["min_version"]:
        out["min_version"] = out["latest_version"]
    return out


async def load_agent_releases(db: AsyncSession) -> Dict[str, Dict[str, str]]:
    defaults = _env_defaults()
    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == KV_KEY))).scalar_one_or_none()
    kv_raw = (row.value if row and isinstance(row.value, dict) else {}) or {}
    return {
        platform: _merge_platform(defaults[platform], kv_raw.get(platform))
        for platform in PLATFORMS
    }


async def save_agent_releases(
    db: AsyncSession,
    payload: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    current = (await db.execute(select(AdminSetting).where(AdminSetting.key == KV_KEY))).scalar_one_or_none()
    existing = (current.value if current and isinstance(current.value, dict) else {}) or {}
    merged_kv = dict(existing)
    for platform in PLATFORMS:
        if platform not in payload:
            continue
        plat = payload[platform] or {}
        merged_kv[platform] = {
            key: str(plat.get(key, "") or "").strip()
            for key in _platform_field()
        }
    if current is None:
        current = AdminSetting(key=KV_KEY, value=merged_kv)
        db.add(current)
    else:
        current.value = merged_kv
    current.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return await load_agent_releases(db)


async def _load_history_raw(db: AsyncSession) -> List[Dict[str, Any]]:
    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == HISTORY_KV_KEY))).scalar_one_or_none()
    raw = row.value if row and isinstance(row.value, list) else []
    return [item for item in raw if isinstance(item, dict)]


async def load_release_history(
    db: AsyncSession,
    *,
    platform: Optional[Platform] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    items = await _load_history_raw(db)
    if platform:
        items = [i for i in items if i.get("platform") == platform]
    items.sort(key=lambda x: str(x.get("published_at") or ""), reverse=True)
    out: List[Dict[str, Any]] = []
    for item in items[:limit]:
        row = dict(item)
        if not row.get("filename"):
            row["filename"] = filename_from_url(str(row.get("download_url") or ""))
        out.append(row)
    return out


def filename_from_url(url: str) -> str:
    """从下载地址解析包名，如 …/sigtrades-agent-macos.dmg → sigtrades-agent-macos.dmg"""
    raw = (url or "").strip()
    if not raw:
        return ""
    path = unquote(urlparse(raw).path or "")
    name = Path(path).name
    return name if name and name not in {".", "/"} else ""


def _resolve_local_release_file(download_url: str, platform: Platform) -> Optional[Path]:
    """把公开下载 URL 映射到 AGENT_RELEASES_DIR 下的本地文件。"""
    root = Path(settings.AGENT_RELEASES_DIR)
    name = filename_from_url(download_url) or LOCAL_FILENAMES.get(platform, "")
    if not name:
        return None
    # 支持 /releases/xxx 与 /releases/archive/xxx
    path_part = unquote(urlparse(download_url).path or "")
    marker = "/releases/"
    if marker in path_part:
        rel = path_part.split(marker, 1)[1].lstrip("/")
        cand = root / rel
        if cand.is_file():
            return cand
    cand = root / name
    if cand.is_file():
        return cand
    if platform == "macos":
        for fb in LOCAL_FILENAME_FALLBACKS.get("macos", ()):
            p = root / fb
            if p.is_file():
                return p
    return None


def archive_published_package(
    platform: Platform,
    version: str,
    download_url: str,
) -> Dict[str, str]:
    """发布时复制一份带版本号的归档，供历史页长期下载。

    返回 filename / download_url（归档成功则指向 archive/；失败则回退原 URL）。
    """
    ver = (version or "").strip().lstrip("vV") or "0.0.0"
    src = _resolve_local_release_file(download_url, platform)
    base_name = filename_from_url(download_url) or (src.name if src else LOCAL_FILENAMES.get(platform, ""))
    if not src or not src.is_file() or not base_name:
        return {
            "filename": base_name,
            "download_url": (download_url or "").strip(),
            "archived": "0",
        }

    stem = Path(base_name).stem
    suffix = Path(base_name).suffix
    # 打包产物已是 …-vX.Y.Z.ext 时不再叠加；去掉无版本别名后的重复缀
    if f"-v{ver}" in stem:
        archived_name = f"{stem}{suffix}"
    else:
        archived_name = f"{stem}-v{ver}{suffix}"

    archive_dir = Path(settings.AGENT_RELEASES_DIR) / "archive"
    dest = archive_dir / archived_name
    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    except OSError as exc:
        # 常见原因：docker 把 agent-releases 挂成 :ro；归档失败不阻断发布
        logger.warning("归档 Agent 包失败 %s → %s: %s", src, dest, exc)
        return {
            "filename": base_name,
            "download_url": (download_url or "").strip(),
            "archived": "0",
        }

    public_url = f"{_releases_public_base()}/archive/{archived_name}"
    return {
        "filename": archived_name,
        "download_url": public_url,
        "archived": "1",
    }


def normalize_version(version: str) -> str:
    return (version or "").strip().lstrip("vV")


async def publish_agent_release(
    db: AsyncSession,
    platform: Platform,
    data: Dict[str, Any],
    *,
    published_by: str = "admin",
    allow_same_version: bool = False,  # 兼容旧调用；同版本始终允许重复发布
) -> Dict[str, Any]:
    plat_data = {
        key: str(data.get(key, "") or "").strip()
        for key in _platform_field()
    }
    if not plat_data["latest_version"]:
        raise ValueError("latest_version required")
    if not plat_data["min_version"]:
        plat_data["min_version"] = plat_data["latest_version"]

    # 先归档（失败不抛），再写入 KV，避免半成功导致无法重发
    archived = archive_published_package(
        platform,
        plat_data["latest_version"],
        plat_data["download_url"],
    )
    await save_agent_releases(db, {platform: plat_data})
    history_url = archived["download_url"] or plat_data["download_url"]
    history_filename = archived["filename"] or filename_from_url(plat_data["download_url"])

    now = datetime.now(timezone.utc)
    entry = {
        "id": str(uuid.uuid4()),
        "platform": platform,
        "version": plat_data["latest_version"],
        "min_version": plat_data["min_version"],
        "download_url": history_url,
        "filename": history_filename,
        "sha256": plat_data["sha256"],
        "release_notes": plat_data["release_notes"],
        "published_at": now.isoformat(),
        "published_at_et": format_et(now),
        "published_by": published_by,
    }

    history = await _load_history_raw(db)
    history.insert(0, entry)
    history = history[:MAX_HISTORY]

    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == HISTORY_KV_KEY))).scalar_one_or_none()
    if row is None:
        row = AdminSetting(key=HISTORY_KV_KEY, value=history)
        db.add(row)
    else:
        row.value = history
    row.updated_at = now
    await db.commit()
    return entry


async def restore_release_history(
    db: AsyncSession,
    entry_id: str,
    *,
    published_by: str = "admin",
) -> Dict[str, Any]:
    history = await _load_history_raw(db)
    entry = next((i for i in history if i.get("id") == entry_id), None)
    if not entry:
        raise LookupError("history entry not found")
    platform = entry.get("platform")
    if platform not in PLATFORMS:
        raise ValueError("invalid platform in history")
    return await publish_agent_release(
        db,
        platform,  # type: ignore[arg-type]
        {
            "latest_version": entry.get("version") or "",
            "min_version": entry.get("min_version") or entry.get("version") or "",
            "download_url": entry.get("download_url") or "",
            "sha256": entry.get("sha256") or "",
            "release_notes": entry.get("release_notes") or "",
        },
        published_by=published_by,
        allow_same_version=True,
    )


async def delete_release_history(db: AsyncSession, entry_id: str) -> Dict[str, Any]:
    """删除一条发布历史；若有 archive/ 归档包则尽量删除本地文件。"""
    history = await _load_history_raw(db)
    entry = next((i for i in history if i.get("id") == entry_id), None)
    if not entry:
        raise LookupError("history entry not found")

    root = Path(settings.AGENT_RELEASES_DIR)
    filename = str(entry.get("filename") or "").strip() or filename_from_url(str(entry.get("download_url") or ""))
    download_url = str(entry.get("download_url") or "")
    candidates: List[Path] = []
    if filename:
        candidates.append(root / "archive" / Path(filename).name)
        # URL 指向 archive/ 时也解析相对路径
        path_part = unquote(urlparse(download_url).path or "")
        marker = "/releases/"
        if marker in path_part:
            rel = path_part.split(marker, 1)[1].lstrip("/")
            if rel.startswith("archive/"):
                candidates.append(root / rel)
    removed_files: List[str] = []
    seen: set[str] = set()
    for cand in candidates:
        key = str(cand.resolve()) if cand.exists() else str(cand)
        if key in seen:
            continue
        seen.add(key)
        if cand.is_file() and "archive" in cand.parts:
            try:
                cand.unlink()
                removed_files.append(str(cand))
            except OSError as exc:
                logger.warning("删除归档包失败 %s: %s", cand, exc)

    new_history = [i for i in history if i.get("id") != entry_id]
    now = datetime.now(timezone.utc)
    row = (await db.execute(select(AdminSetting).where(AdminSetting.key == HISTORY_KV_KEY))).scalar_one_or_none()
    if row is None:
        row = AdminSetting(key=HISTORY_KV_KEY, value=new_history)
        db.add(row)
    else:
        row.value = new_history
    row.updated_at = now
    await db.commit()
    return {"entry": entry, "removed_files": removed_files}


def platform_public_payload(platform: Platform, data: Dict[str, str]) -> Dict[str, Any]:
    latest = data.get("latest_version") or settings.AGENT_LATEST_VERSION
    min_ver = data.get("min_version") or latest
    download_url = data.get("download_url") or ""
    sha256 = data.get("sha256") or ""
    filename = filename_from_url(download_url) or LOCAL_FILENAMES.get(platform, "")
    return {
        "platform": platform,
        "latest_version": latest,
        "min_version": min_ver,
        "download_url": download_url,
        "filename": filename,
        "sha256": sha256,
        "release_notes": data.get("release_notes") or "",
    }


def public_history_item(entry: Dict[str, Any]) -> Dict[str, Any]:
    """历史记录对用户可见字段。"""
    url = str(entry.get("download_url") or "").strip()
    filename = str(entry.get("filename") or "").strip() or filename_from_url(url)
    return {
        "id": entry.get("id") or "",
        "platform": entry.get("platform") or "",
        "version": entry.get("version") or "",
        "filename": filename,
        "download_url": url,
        "sha256": entry.get("sha256") or "",
        "release_notes": entry.get("release_notes") or "",
        "published_at": entry.get("published_at") or "",
        "published_at_et": entry.get("published_at_et") or "",
    }


def _releases_public_base() -> str:
    base = (settings.AGENT_RELEASES_PUBLIC_BASE or "").strip().rstrip("/")
    if base:
        return base
    # 回退：从已有下载 URL 推导目录
    for url in (settings.AGENT_DOWNLOAD_URL, settings.AGENT_WINDOWS_DOWNLOAD_URL):
        u = (url or "").strip()
        if u and "/" in u:
            return u.rsplit("/", 1)[0]
    return "http://localhost:8080/releases"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bump_patch_version(version: str) -> str:
    """0.1.0 → 0.1.1；无法解析则原样返回。"""
    raw = (version or "").strip().lstrip("vV")
    if not raw:
        return "0.1.0"
    parts = raw.split(".")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return raw
    while len(nums) < 3:
        nums.append(0)
    nums[2] += 1
    return ".".join(str(n) for n in nums[:3])


def _newest_versioned_package(root: Path, platform: Platform) -> Optional[Path]:
    pattern = LOCAL_VERSIONED_GLOBS.get(platform)
    if not pattern:
        return None
    matches = [p for p in root.glob(pattern) if p.is_file()]
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def scan_local_agent_packages() -> Dict[str, Any]:
    """扫描 AGENT_RELEASES_DIR，返回可填入后台的 macOS/Windows 包信息。"""
    root = Path(settings.AGENT_RELEASES_DIR)
    public_base = _releases_public_base()
    manifest: Dict[str, Any] = {}
    manifest_path = root / "latest-manifest.json"
    if manifest_path.is_file():
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                manifest = raw
        except Exception:  # noqa: BLE001
            manifest = {}

    manifest_platforms = manifest.get("platforms") if isinstance(manifest.get("platforms"), dict) else {}
    platforms_out: Dict[str, Any] = {}
    for platform, alias_name in LOCAL_FILENAMES.items():
        mf = manifest_platforms.get(platform) if isinstance(manifest_platforms.get(platform), dict) else {}
        path: Optional[Path] = None
        chosen = alias_name

        # 1) 清单中的带版本文件名（优先）
        mf_name = str(mf.get("filename") or "").strip()
        if mf_name:
            cand = root / mf_name
            if cand.is_file():
                path = cand
                chosen = mf_name

        # 2) 目录内最新带版本包
        if path is None:
            newest = _newest_versioned_package(root, platform)
            if newest is not None:
                path = newest
                chosen = newest.name

        # 3) 无版本别名 / zip 回退
        if path is None:
            for name in (alias_name,) + LOCAL_FILENAME_FALLBACKS.get(platform, ()):
                cand = root / name
                if cand.is_file():
                    path = cand
                    chosen = name
                    break

        entry: Dict[str, Any] = {
            "platform": platform,
            "filename": chosen,
            "exists": path is not None,
            "path": str(path) if path is not None else "",
            "download_url": "",
            "sha256": "",
            "size_bytes": 0,
            "mtime": None,
            "version_hint": "",
            "built_at": None,
        }
        if path is not None:
            st = path.stat()
            entry["size_bytes"] = int(st.st_size)
            entry["mtime"] = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat()
            # 清单 sha 与文件一致时复用，否则重算
            mf_sha = str(mf.get("sha256") or "").strip().lower()
            if mf_sha and str(mf.get("filename") or "") == chosen:
                # 仍校验 size，避免陈旧清单
                mf_size = mf.get("size_bytes")
                if mf_size is None or int(mf_size) == int(st.st_size):
                    entry["sha256"] = mf_sha
                else:
                    entry["sha256"] = _sha256_file(path)
            else:
                entry["sha256"] = _sha256_file(path)
            entry["download_url"] = f"{public_base}/{chosen}"
            entry["version_hint"] = str(mf.get("version") or manifest.get("version") or "").strip()
            entry["built_at"] = mf.get("built_at") or entry["mtime"]
        platforms_out[platform] = entry

    return {
        "releases_dir": str(root),
        "public_base": public_base,
        "manifest": manifest or None,
        "platforms": platforms_out,
    }
