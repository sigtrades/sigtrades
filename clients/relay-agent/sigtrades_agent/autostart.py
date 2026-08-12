"""开机自启安装/卸载（跨平台，后台静默）。

- macOS: ~/Library/LaunchAgents/app.sigtrades.agent.plist (RunAtLoad + KeepAlive)
- Windows: 注册表 HKCU\\...\\Run 写入 agent 路径
- Linux: ~/.config/systemd/user/sigtrades-agent.service

可执行路径优先取打包后的可执行文件（PyInstaller），否则回退到 `python -m sigtrades_agent`。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

APP_LABEL = "app.sigtrades.agent"


def _agent_invocation() -> list[str]:
    """返回启动 agent 的命令行（打包后为单个可执行文件）。"""
    if getattr(sys, "frozen", False):
        return [sys.executable]  # PyInstaller 单文件
    return [sys.executable, "-m", "sigtrades_agent"]


# ----------------------------- macOS -----------------------------
def _mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{APP_LABEL}.plist"


def _install_mac() -> Path:
    args = _agent_invocation() + ["--no-window"]
    program_args = "\n".join(f"        <string>{a}</string>" for a in args)
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>{APP_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>RunAtLoad</key><true/>
    <key>KeepAlive</key><true/>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
"""
    path = _mac_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plist, encoding="utf-8")
    subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
    subprocess.run(["launchctl", "load", str(path)], capture_output=True)
    return path


def _uninstall_mac() -> None:
    path = _mac_plist_path()
    if path.exists():
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        path.unlink()


# ----------------------------- Windows -----------------------------
def _install_windows() -> str:
    import winreg  # type: ignore

    cmd = " ".join(f'"{a}"' for a in _agent_invocation()) + " --no-window"
    key = winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0, winreg.KEY_SET_VALUE,
    )
    winreg.SetValueEx(key, "sigtrades-agent", 0, winreg.REG_SZ, cmd)
    winreg.CloseKey(key)
    return cmd


def _uninstall_windows() -> None:
    import winreg  # type: ignore

    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE,
        )
        winreg.DeleteValue(key, "sigtrades-agent")
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


# ----------------------------- Linux -----------------------------
def _linux_unit_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / "sigtrades-agent.service"


def _install_linux() -> Path:
    exec_start = " ".join(_agent_invocation()) + " --no-window"
    unit = f"""[Unit]
Description=sigtrades Relay Agent
After=network-online.target

[Service]
ExecStart={exec_start}
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""
    path = _linux_unit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(unit, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "enable", "--now", "sigtrades-agent"], capture_output=True)
    return path


def _uninstall_linux() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", "sigtrades-agent"], capture_output=True)
    path = _linux_unit_path()
    if path.exists():
        path.unlink()


# ----------------------------- 入口 -----------------------------
def install_autostart() -> str:
    if sys.platform == "darwin":
        return str(_install_mac())
    if sys.platform.startswith("win"):
        return _install_windows()
    return str(_install_linux())


def uninstall_autostart() -> None:
    if sys.platform == "darwin":
        _uninstall_mac()
    elif sys.platform.startswith("win"):
        _uninstall_windows()
    else:
        _uninstall_linux()


def autostart_installed() -> bool:
    if sys.platform == "darwin":
        return _mac_plist_path().exists()
    if sys.platform.startswith("win"):
        try:
            import winreg  # type: ignore

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_READ,
            )
            winreg.QueryValueEx(key, "sigtrades-agent")
            winreg.CloseKey(key)
            return True
        except OSError:
            return False
    return _linux_unit_path().exists()
