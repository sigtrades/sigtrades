"""自定义协议 sigtrades-agent:// — 从浏览器唤起桌面 Agent 窗口。

- macOS：打包进 .app 的 Info.plist（CFBundleURLTypes）
- Windows：首次启动写入 HKCU\\Software\\Classes\\sigtrades-agent
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

logger = logging.getLogger("sigtrades-agent.deep-link")

SCHEME = "sigtrades-agent"
OPEN_URL = f"{SCHEME}://open"


def is_deep_link(arg: str) -> bool:
    a = (arg or "").strip().lower()
    return a.startswith(f"{SCHEME}://")


def extract_deep_link(argv: Optional[list[str]] = None) -> Optional[str]:
    for a in argv if argv is not None else sys.argv[1:]:
        if is_deep_link(a):
            return a.strip()
    return None


def ensure_protocol_registered() -> None:
    """尽量注册协议处理器（失败不影响启动）。"""
    if sys.platform.startswith("win"):
        _register_windows()
    # macOS 依赖 .app Info.plist；开发态 python -m 无法稳定注册


def _register_windows() -> None:
    try:
        import winreg  # type: ignore
    except ImportError:
        return

    exe = sys.executable
    if not exe:
        return
    # 命令行：exe "%1"
    cmd = f'"{exe}" "%1"'
    try:
        root = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{SCHEME}")
        winreg.SetValueEx(root, None, 0, winreg.REG_SZ, "URL:sigtrades Agent")
        winreg.SetValueEx(root, "URL Protocol", 0, winreg.REG_SZ, "")
        winreg.CloseKey(root)

        icon = winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{SCHEME}\DefaultIcon")
        winreg.SetValueEx(icon, None, 0, winreg.REG_SZ, f'"{exe}",0')
        winreg.CloseKey(icon)

        command = winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{SCHEME}\shell\open\command"
        )
        winreg.SetValueEx(command, None, 0, winreg.REG_SZ, cmd)
        winreg.CloseKey(command)
        logger.info("已注册协议 %s:// → %s", SCHEME, exe)
    except Exception as e:  # noqa: BLE001
        logger.warning("注册协议失败: %s", e)
