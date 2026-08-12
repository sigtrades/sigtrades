"""Agent 入口：本机 Relay + 内置 React UI（pywebview）+ 可选托盘。"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import signal as os_signal
import sys
import threading

from sigtrades_agent import __version__
from sigtrades_agent.agent_local_api import AgentLocalApi, LOCAL_HOST, LOCAL_PORT
from sigtrades_agent.client import RelayAgent
from sigtrades_agent.config import AgentConfig, load_config, save_config, config_path
from sigtrades_agent.discord_bridge import DiscordBridge
from sigtrades_agent.gateway_probe import probe_all_profiles

logger = logging.getLogger("sigtrades-agent")


def _notify_user(title: str, message: str) -> None:
    """打包后无控制台时，用系统弹窗提示（避免双击后「没反应」）。"""
    if sys.platform == "darwin":
        with contextlib.suppress(Exception):
            import subprocess

            # 避免引号打断 AppleScript
            def _esc(s: str) -> str:
                return s.replace("\\", "\\\\").replace('"', '\\"')

            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display alert "{_esc(title)}" message "{_esc(message)}"',
                ],
                check=False,
                capture_output=True,
            )
            return
    if sys.platform.startswith("win"):
        with contextlib.suppress(Exception):
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
            return
    logger.info("%s: %s", title, message)


def _ensure_single_instance() -> None:
    import socket
    import urllib.error
    import urllib.request

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((LOCAL_HOST, LOCAL_PORT))
    except OSError:
        health_url = f"http://{LOCAL_HOST}:{LOCAL_PORT}/health"
        show_url = f"http://{LOCAL_HOST}:{LOCAL_PORT}/api/show"
        try:
            with urllib.request.urlopen(health_url, timeout=1.5) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if resp.status == 200 and "sigtrades-agent" in body:
                    logger.info("Agent 已在运行，唤起设置窗口")
                    req = urllib.request.Request(show_url, method="POST", data=b"{}")
                    req.add_header("Content-Type", "application/json")
                    with contextlib.suppress(Exception):
                        urllib.request.urlopen(req, timeout=1.5).read()
                    raise SystemExit(0)
        except urllib.error.URLError:
            pass
        logger.error("端口 %s 被占用，请释放后重试", LOCAL_PORT)
        _notify_user(
            "sigtrades Agent",
            f"端口 {LOCAL_PORT} 被占用，无法启动。\n请先执行：pkill -f sigtrades-agent\n然后重新打开。",
        )
        raise SystemExit(1)
    finally:
        sock.close()


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _try_start_tray(state_holder: dict, language: str = "zh") -> None:
    from sigtrades_agent import app_lifecycle

    try:
        import pystray
        from PIL import Image, ImageDraw
    except Exception:  # noqa: BLE001
        logger.info("未安装托盘依赖(pystray/Pillow)，跳过系统托盘")
        app_lifecycle.set_tray(None, active=False)
        return

    en = (language or "zh").lower().startswith("en")
    offline = "offline" if en else "离线"
    online_l = "online" if en else "在线"
    title_base = "sigtrades agent"

    from sigtrades_agent.branding import logo_png

    _logo_path = logo_png()
    _logo_base = None
    if _logo_path is not None:
        with contextlib.suppress(Exception):
            _logo_base = Image.open(_logo_path).convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)

    def make_icon(online: bool):
        if _logo_base is not None:
            img = _logo_base.copy()
            # 右下角状态点：在线绿 / 离线灰
            d = ImageDraw.Draw(img)
            color = (16, 185, 129, 255) if online else (148, 163, 184, 255)
            d.ellipse((44, 44, 60, 60), fill=color, outline=(15, 23, 42, 255))
            return img
        img = Image.new("RGB", (64, 64), "white")
        d = ImageDraw.Draw(img)
        d.ellipse((12, 12, 52, 52), fill=(46, 204, 113) if online else (149, 165, 166))
        return img

    icon = pystray.Icon("sigtrades", make_icon(False), f"{title_base}: {offline}")

    def refresh():
        online = state_holder.get("online", False)
        icon.icon = make_icon(online)
        icon.title = f"{title_base}: {online_l if online else offline}"

    def show_window(_icon, _item):
        try:
            from sigtrades_agent.desktop_window import focus_agent_window

            focus_agent_window()
        except Exception as e:  # noqa: BLE001
            logger.warning("无法打开窗口: %s", e)

    def quit_app(_icon, _item):
        app_lifecycle.request_quit(reason="tray")

    menu = pystray.Menu(
        pystray.MenuItem("Open" if en else "打开设置", show_window, default=True),
        pystray.MenuItem("Quit" if en else "退出", quit_app),
    )
    icon.menu = menu
    state_holder["_refresh"] = refresh
    app_lifecycle.set_tray(icon, active=True)
    # macOS：禁止在后台线程 icon.run()（会与 pywebview 抢 NSApp 主循环导致秒退）。
    # 真正挂接在 desktop_window.start → attach_tray_to_mainloop → run_detached。
    if sys.platform == "darwin":
        return
    threading.Thread(target=icon.run, daemon=True).start()


def _check_agent_version() -> None:
    from sigtrades_agent.cloud_defaults import DEFAULT_VERSION_CHECK_URL

    url = os.getenv("SIGTRADES_VERSION_CHECK_URL", DEFAULT_VERSION_CHECK_URL).strip()
    if not url:
        return
    try:
        from sigtrades_agent.updater import check_and_update

        check_and_update(__version__, auto_apply=True)
    except Exception as e:  # noqa: BLE001
        logger.debug("version check skipped: %s", e)


def _run_agent_async(
    cfg: AgentConfig,
    state_holder: dict,
    stop_event: threading.Event,
) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def on_state(online: bool, brokers: dict, gateways=None):
        state_holder["online"] = online
        state_holder["brokers"] = brokers
        if gateways is not None:
            state_holder["gateways"] = gateways
        refresh = state_holder.get("_refresh")
        if refresh:
            refresh()

    stats = state_holder.setdefault("stats", {"session_received": 0, "session_failed": 0})
    agent = RelayAgent(cfg, on_state=on_state, stats=stats)
    discord_bridge = DiscordBridge()

    async def do_login() -> AgentConfig:
        from sigtrades_agent.browser_login import login_via_browser
        from sigtrades_agent.desktop_window import focus_agent_window

        updated = login_via_browser(load_config())
        agent.config.user_token = updated.user_token
        agent.config.relay_url = updated.relay_url
        agent.config.account_email = updated.account_email
        # 清 stop 并踢掉可能残留的旧 WS，避免旧 finally 干扰 presence
        agent.reconnect_after_login()
        # 登录后重试离线券商（仅 probe 不会真正拉起连接）
        try:
            await agent.reconnect_all_profiles(only_offline=True)
        except Exception as e:  # noqa: BLE001
            logger.warning("登录后券商重连未全部完成: %s", e)
        focus_agent_window()
        return updated

    def do_logout() -> None:
        agent.config.user_token = ""
        # 只断云端；本地 IBKR/富途执行器保留，避免重登后还要全量冷启动
        agent.disconnect_cloud()

    def do_quit() -> None:
        from sigtrades_agent import app_lifecycle

        app_lifecycle.request_quit(reason="ui")

    def do_show() -> None:
        from sigtrades_agent.desktop_window import focus_agent_window

        focus_agent_window()

    local_api = AgentLocalApi(
        discord_bridge,
        state_holder=state_holder,
        version=__version__,
        on_login=do_login,
        on_logout=do_logout,
        on_quit=do_quit,
        on_show=do_show,
        on_config_apply=agent.apply_config,
        on_probe_all=agent.refresh_gateway_status,
        on_reconnect=agent.reconnect_profile,
        on_relay_stop=agent.stop_relay,
        on_relay_reconnect=agent.reconnect_relay,
        relay_held_getter=lambda: bool(getattr(agent, "_relay_hold", False)),
    )

    async def shutdown() -> None:
        logger.info("正在停止...")
        agent.stop()
        await discord_bridge.stop()
        await local_api.stop()

    async def run_all() -> None:
        await local_api.start()
        agent_task = asyncio.create_task(agent.run())

        while not stop_event.is_set():
            if agent_task.done():
                exc = agent_task.exception()
                if exc:
                    logger.debug("Agent relay loop ended: %s", exc)
                cfg_now = load_config()
                if cfg_now.user_token:
                    agent.config.user_token = cfg_now.user_token
                    agent.config.relay_url = cfg_now.relay_url
                    agent.config.account_email = cfg_now.account_email
                    agent.reconnect_after_login()
                    agent_task = asyncio.create_task(agent.run())
            await asyncio.sleep(0.5)

        agent.stop()
        await agent_task

    try:
        loop.run_until_complete(run_all())
    except KeyboardInterrupt:
        agent.stop()
    finally:
        loop.run_until_complete(shutdown())
        loop.close()


def main(argv=None) -> int:
    from sigtrades_agent.deep_link import ensure_protocol_registered, extract_deep_link, is_deep_link

    raw = list(argv) if argv is not None else sys.argv[1:]
    # 浏览器唤起：sigtrades-agent://open — 需在 argparse 前剥离
    deep_link = extract_deep_link(raw)
    cleaned = [a for a in raw if not is_deep_link(a)]

    parser = argparse.ArgumentParser(prog="sigtrades-agent", description="sigtrades Relay Agent")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--show-config", action="store_true", help="打印配置文件路径后退出")
    parser.add_argument("--token", help="设置 user_token 并保存")
    parser.add_argument("--login", action="store_true", help="通过浏览器登录")
    parser.add_argument("--relay-url", help="设置 relay url 并保存")
    parser.add_argument("--no-tray", action="store_true", help="禁用系统托盘")
    parser.add_argument("--no-window", action="store_true", help="不打开桌面窗口（纯后台）")
    parser.add_argument("--install-autostart", action="store_true", help="安装开机自启后退出")
    parser.add_argument("--uninstall-autostart", action="store_true", help="卸载开机自启后退出")
    parser.add_argument("--check-update", action="store_true", help="检查更新后退出")
    args = parser.parse_args(cleaned)

    _setup_logging(args.verbose)
    if deep_link:
        logger.info("收到深链接: %s", deep_link)
    # Windows 注册协议；已运行时下面 single-instance 会 POST /api/show 唤起窗口
    ensure_protocol_registered()

    if args.show_config:
        print(config_path())
        return 0

    if args.install_autostart:
        from sigtrades_agent.autostart import install_autostart

        print("已安装开机自启:", install_autostart())
        return 0

    if args.uninstall_autostart:
        from sigtrades_agent.autostart import uninstall_autostart

        uninstall_autostart()
        print("已卸载开机自启")
        return 0

    if args.check_update:
        from sigtrades_agent.updater import check_and_update

        info = check_and_update(__version__, auto_apply=False)
        if info:
            print(f"新版本 {info['latest_version']} 可用: {info.get('download_url', '')}")
        else:
            print(f"已是最新版本 ({__version__})")
        return 0

    cfg = load_config()
    changed = False
    if args.token:
        cfg.user_token = args.token
        changed = True
    if args.relay_url:
        cfg.relay_url = args.relay_url
        changed = True
    if changed:
        save_config(cfg)
        logger.info("配置已更新: %s", config_path())

    headless = args.no_window
    if args.login or (not cfg.user_token and headless):
        from sigtrades_agent.browser_login import login_via_browser

        try:
            cfg = login_via_browser(cfg)
        except Exception as e:  # noqa: BLE001
            logger.error("浏览器登录失败: %s", e)
            return 2

    # 单实例检查尽量靠前：避免二次点击时先探测网关（Dock 跳很久再退出）
    _ensure_single_instance()
    _check_agent_version()
    gateways0 = probe_all_profiles(cfg.broker_profiles)

    state_holder: dict = {"online": False, "brokers": {}, "gateways": gateways0}
    stop_event = threading.Event()

    from sigtrades_agent import app_lifecycle

    app_lifecycle.configure(stop_event=stop_event)

    if not args.no_tray:
        _try_start_tray(state_holder, cfg.language)

    worker = threading.Thread(
        target=_run_agent_async,
        args=(cfg, state_holder, stop_event),
        daemon=True,
    )
    worker.start()

    def _shutdown(*_):
        app_lifecycle.request_quit(reason="signal")

    for sig in (os_signal.SIGINT, os_signal.SIGTERM):
        try:
            os_signal.signal(sig, _shutdown)
        except NotImplementedError:
            pass

    if headless:
        try:
            worker.join()
        except KeyboardInterrupt:
            app_lifecycle.request_quit(reason="keyboard")
            worker.join(timeout=5)
        return 0

    from sigtrades_agent.desktop_window import start_desktop_window

    try:
        start_desktop_window()
    except KeyboardInterrupt:
        app_lifecycle.request_quit(reason="keyboard")
    finally:
        stop_event.set()
        worker.join(timeout=8)
    return 0


if __name__ == "__main__":
    sys.exit(main())
