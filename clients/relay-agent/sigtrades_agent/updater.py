"""Agent 自动更新：检查版本、下载安装包、校验、重启。"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger("sigtrades-agent.updater")


def _parse_version(v: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", v or "0")
    return tuple(int(p) for p in parts) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse_version(latest) > _parse_version(current)


def _platform_query_suffix() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform == "win32":
        return "windows"
    return "linux"


def check_for_update(url: str, current: str) -> Optional[Dict[str, Any]]:
    import httpx

    plat = _platform_query_suffix()
    sep = "&" if "?" in url else "?"
    check_url = f"{url}{sep}platform={plat}"

    resp = httpx.get(check_url, timeout=10.0)
    resp.raise_for_status()
    data = resp.json()
    latest = data.get("latest_version") or data.get("version") or ""
    if not latest or not is_newer(latest, current):
        return None
    return {
        "latest_version": latest,
        "download_url": data.get("download_url") or "",
        "release_notes": data.get("release_notes") or "",
        "sha256": data.get("sha256") or "",
    }


def _updates_dir() -> Path:
    from sigtrades_agent.config import default_config_dir

    d = default_config_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _verify_sha256(path: Path, expected: str) -> bool:
    if not expected:
        logger.warning("更新包未提供 sha256，跳过校验")
        return True
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    actual = h.hexdigest()
    if actual.lower() != expected.lower():
        logger.error("sha256 校验失败: expected=%s actual=%s", expected, actual)
        return False
    return True


def download_update(download_url: str, version: str, *, expected_sha256: str = "") -> Path:
    import httpx

    if not download_url:
        raise ValueError("missing download_url")
    ext = Path(urlparse(download_url).path).suffix or ".bin"
    dest = _updates_dir() / f"sigtrades-agent-{version}{ext}"
    with httpx.stream("GET", download_url, timeout=120.0, follow_redirects=True) as resp:
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_bytes():
                f.write(chunk)
    if not _verify_sha256(dest, expected_sha256):
        dest.unlink(missing_ok=True)
        raise ValueError("sha256 verification failed")
    logger.info("已下载更新包: %s", dest)
    return dest


def _restart_self() -> None:
    """替换二进制后重启当前进程。"""
    logger.info("正在重启 Agent 以应用更新…")
    os.execv(sys.executable, [sys.executable] + sys.argv)


def apply_update(artifact: Path, *, restart: bool = True) -> bool:
    """尽力应用更新：zip 解压后替换当前可执行文件（PyInstaller onefile）。"""
    if not artifact.exists():
        return False
    if artifact.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="sigtrades-update-"))
        with zipfile.ZipFile(artifact, "r") as zf:
            zf.extractall(tmp)
        candidates = list(tmp.rglob("sigtrades-agent*")) + list(tmp.rglob("sigtrades_agent*"))
        candidates = [c for c in candidates if c.is_file() and os.access(c, os.X_OK)]
        if not candidates and sys.platform == "win32":
            candidates = list(tmp.rglob("*.exe"))
        if not candidates:
            logger.error("更新包内未找到可执行文件")
            return False
        new_bin = candidates[0]
        target = Path(sys.argv[0]).resolve()
        if getattr(sys, "frozen", False):
            backup = target.with_suffix(target.suffix + ".bak")
            shutil.copy2(target, backup)
            shutil.copy2(new_bin, target)
            if sys.platform != "win32":
                os.chmod(target, 0o755)
            logger.info("已替换 Agent 二进制: %s（备份 %s）", target, backup)
            if restart:
                _restart_self()
            return True
        logger.info("非 frozen 模式，更新包已保存: %s", artifact)
        return False

    if sys.platform == "darwin" and artifact.suffix.lower() == ".dmg":
        logger.info("macOS .dmg 更新包已下载，请手动安装: %s", artifact)
        subprocess.run(["open", str(artifact)], check=False)
        return False

    logger.info("更新包已保存: %s", artifact)
    return False


def check_and_update(current: str, *, auto_apply: bool = True) -> Optional[Dict[str, Any]]:
    from sigtrades_agent.cloud_defaults import DEFAULT_VERSION_CHECK_URL

    url = os.getenv("SIGTRADES_VERSION_CHECK_URL", DEFAULT_VERSION_CHECK_URL).strip()
    if not url:
        return None
    info = check_for_update(url, current)
    if not info:
        return None
    logger.warning(
        "Agent 新版本: %s（当前 %s）%s",
        info["latest_version"],
        current,
        info.get("release_notes", ""),
    )
    dl = info.get("download_url") or ""
    if not dl:
        return info
    if os.getenv("SIGTRADES_AUTO_UPDATE", "true").lower() not in ("1", "true", "yes"):
        logger.info("自动更新已禁用（SIGTRADES_AUTO_UPDATE=false）")
        return info
    try:
        path = download_update(dl, info["latest_version"], expected_sha256=info.get("sha256") or "")
        info["local_path"] = str(path)
        if auto_apply:
            info["applied"] = apply_update(path, restart=True)
    except Exception as e:  # noqa: BLE001
        logger.error("自动更新失败: %s", e)
        info["error"] = str(e)
    return info
