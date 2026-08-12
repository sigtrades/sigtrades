"""pywebview 桌面窗口：加载本机 Agent UI。"""

from __future__ import annotations

import contextlib
import logging
import threading

from sigtrades_agent.agent_local_api import LOCAL_HOST, LOCAL_PORT
from sigtrades_agent import app_lifecycle

logger = logging.getLogger("desktop-window")

WINDOW_WIDTH = 420
WINDOW_HEIGHT = 560
MIN_WIDTH = 360
MIN_HEIGHT = 480


def ui_url(*, query: str = "") -> str:
    base = f"http://{LOCAL_HOST}:{LOCAL_PORT}/ui/"
    return f"{base}?{query}" if query else base


def _activate_macos_app() -> None:
    """把进程拉到前台（否则有时只在托盘跑、窗口被挡在后面）。"""
    if __import__("sys").platform != "darwin":
        return
    with contextlib.suppress(Exception):
        from AppKit import NSApp

        NSApp.activateIgnoringOtherApps_(True)


def focus_agent_window() -> None:
    """登录完成 / 二次点击图标时，把 Agent 窗口带到前台。"""
    try:
        import webview

        if not webview.windows:
            logger.warning("focus_agent_window: 尚无窗口")
            return
        win = webview.windows[0]
        with contextlib.suppress(Exception):
            win.show()
        with contextlib.suppress(Exception):
            win.restore()
        with contextlib.suppress(Exception):
            # pywebview ≥4
            win.activate()
        _activate_macos_app()
        logger.info("已唤起 Agent 窗口")
    except Exception as e:  # noqa: BLE001
        logger.warning("无法聚焦 Agent 窗口: %s", e)


def start_desktop_window(*, hidden: bool = False) -> None:
    """阻塞当前线程直到所有窗口关闭（应在主线程调用）。"""
    try:
        import webview
    except ImportError:
        logger.warning("未安装 pywebview，跳过桌面窗口。pip install pywebview")
        return

    app_lifecycle.install_platform_quit_hooks()

    url = ui_url()
    window = webview.create_window(
        "sigtrades Agent",
        url,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(MIN_WIDTH, MIN_HEIGHT),
        hidden=hidden,
    )

    def on_closing():
        # 显式退出（菜单/托盘/API/Cmd+Q）→ 允许关闭
        if app_lifecycle.quit_requested():
            return True
        # 有托盘：点窗口关闭只隐藏到托盘；无托盘：关闭即退出
        # 注意：macOS Cmd+Q 走 applicationShouldTerminate，不会卡在这里
        if app_lifecycle.tray_active():
            window.hide()
            return False
        app_lifecycle.request_quit(reason="window-close")
        return True

    def on_shown():
        _activate_macos_app()
        with contextlib.suppress(Exception):
            window.show()

    window.events.closing += on_closing
    with contextlib.suppress(Exception):
        window.events.shown += on_shown
    logger.info("打开桌面窗口: %s", url)
    # 必须在 webview.start（主循环）之前挂接托盘
    app_lifecycle.attach_tray_to_mainloop()
    try:
        webview.start(debug=False)
    except Exception as e:  # noqa: BLE001
        logger.exception("桌面窗口启动失败: %s", e)
        with contextlib.suppress(Exception):
            import webbrowser

            webbrowser.open(url)
        raise


def start_desktop_window_thread(*, hidden: bool = False) -> threading.Thread:
    t = threading.Thread(target=start_desktop_window, kwargs={"hidden": hidden}, daemon=True)
    t.start()
    return t
