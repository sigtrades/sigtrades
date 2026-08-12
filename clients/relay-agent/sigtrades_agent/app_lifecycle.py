"""进程退出协调：托盘 / 菜单 / 信号 / 窗口关闭共用。"""

from __future__ import annotations

import contextlib
import logging
import os
import signal
import sys
import threading
from typing import Any, Optional

logger = logging.getLogger("app-lifecycle")

_lock = threading.Lock()
_quit_requested = threading.Event()
_stop_event: Optional[threading.Event] = None
_tray_icon: Any = None
_tray_active = False
_macos_quit_patched = False


def configure(*, stop_event: threading.Event) -> None:
    global _stop_event
    _stop_event = stop_event


def set_tray(icon: Any | None, *, active: bool) -> None:
    global _tray_icon, _tray_active
    with _lock:
        _tray_icon = icon
        _tray_active = bool(active and icon is not None)


def tray_active() -> bool:
    return _tray_active


def tray_icon() -> Any | None:
    return _tray_icon


def quit_requested() -> bool:
    return _quit_requested.is_set()


def attach_tray_to_mainloop() -> None:
    """macOS：托盘必须挂到与 pywebview 同一 NSApplication 主循环。

    若在后台线程调用 ``icon.run()``，会再跑一套 ``NSApp.run()``，
    常见表现是 Dock 跳几下后进程自行退出。
    """
    if sys.platform != "darwin":
        return
    icon = _tray_icon
    if icon is None:
        return
    try:
        # run_detached：只注册状态栏，不抢主循环（交给 webview.start）
        icon.run_detached()
        logger.debug("托盘已挂到主循环 (run_detached)")
    except Exception as exc:  # noqa: BLE001
        logger.warning("托盘 run_detached 失败，菜单栏图标可能不可用: %s", exc)


def install_platform_quit_hooks() -> None:
    """macOS：菜单「退出」/ Cmd+Q 必须真正退出（不能被「关窗隐藏」拦截）。"""
    global _macos_quit_patched
    if sys.platform != "darwin" or _macos_quit_patched:
        return
    try:
        import Foundation
        from webview.platforms import cocoa
    except Exception:  # noqa: BLE001
        return

    def application_should_terminate(_self, _app):
        request_quit(reason="macos-quit")
        return Foundation.YES

    cocoa.BrowserView.AppDelegate.applicationShouldTerminate_ = application_should_terminate
    _macos_quit_patched = True
    logger.debug("已挂钩 macOS Cmd+Q / 菜单退出")


def request_quit(*, reason: str = "") -> None:
    """请求完整退出：停 worker、停托盘、销毁窗口。"""
    if _quit_requested.is_set():
        return
    _quit_requested.set()
    if reason:
        logger.info("退出 Agent: %s", reason)
    else:
        logger.info("退出 Agent")

    if _stop_event is not None:
        _stop_event.set()

    icon = _tray_icon
    if icon is not None:
        with contextlib.suppress(Exception):
            icon.stop()

    with contextlib.suppress(Exception):
        import webview

        for window in list(getattr(webview, "windows", []) or []):
            with contextlib.suppress(Exception):
                window.destroy()

    # 兜底：部分平台 destroy 后 start() 仍不返回
    def _force_exit() -> None:
        with contextlib.suppress(Exception):
            os.kill(os.getpid(), signal.SIGTERM)
        os._exit(0)

    threading.Timer(1.0, _force_exit).start()
