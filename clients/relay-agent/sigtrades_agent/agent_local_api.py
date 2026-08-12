"""本机 Agent API：Discord 桥接 + 桌面 UI 静态资源 + 配置/状态。"""

from __future__ import annotations

import inspect
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from aiohttp import web

from sigtrades_agent.config import AgentConfig, BrokerProfile, load_config, save_config
from sigtrades_agent.discord_bridge import DiscordBridge
from sigtrades_agent.gateway_probe import probe_broker, probe_profiles
from sigtrades_agent.ui_paths import ui_dist_dir

logger = logging.getLogger("agent-local-api")

LOCAL_HOST = "127.0.0.1"
LOCAL_PORT = 17890

OnConfigApply = Callable[[AgentConfig], Awaitable[dict]]
OnProbeAll = Callable[[], Awaitable[list]]
OnReconnect = Callable[[str, str], Awaitable[dict]]
OnRelayAction = Callable[[], Awaitable[dict]]


def _cors(response: web.StreamResponse) -> web.StreamResponse:
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


async def _json(request: web.Request, handler):
    if request.method == "OPTIONS":
        return _cors(web.Response(status=204))
    try:
        data = await handler(request)
        return _cors(web.json_response(data))
    except ValueError as e:
        return _cors(web.json_response({"error": str(e)}, status=400))
    except Exception as e:  # noqa: BLE001
        logger.exception("local api error")
        return _cors(web.json_response({"error": str(e)}, status=500))


class AgentLocalApi:
    def __init__(
        self,
        bridge: DiscordBridge,
        *,
        state_holder: dict,
        version: str,
        on_login: Optional[Callable[[], AgentConfig | Awaitable[AgentConfig]]] = None,
        on_logout: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_show: Optional[Callable[[], None]] = None,
        on_config_apply: Optional[OnConfigApply] = None,
        on_probe_all: Optional[OnProbeAll] = None,
        on_reconnect: Optional[OnReconnect] = None,
        on_relay_stop: Optional[OnRelayAction] = None,
        on_relay_reconnect: Optional[OnRelayAction] = None,
        relay_held_getter: Optional[Callable[[], bool]] = None,
    ) -> None:
        self.bridge = bridge
        self.state_holder = state_holder
        self.version = version
        self._on_login = on_login
        self._on_logout = on_logout
        self._on_quit = on_quit
        self._on_show = on_show
        self._on_config_apply = on_config_apply
        self._on_probe_all = on_probe_all
        self._on_reconnect = on_reconnect
        self._on_relay_stop = on_relay_stop
        self._on_relay_reconnect = on_relay_reconnect
        self._relay_held_getter = relay_held_getter
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._ui_root = ui_dist_dir()

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_route("*", "/health", self._health)
        app.router.add_route("*", "/api/status", self._status)
        app.router.add_route("*", "/api/config", self._config)
        app.router.add_route("*", "/api/login", self._login)
        app.router.add_route("*", "/api/logout", self._logout)
        app.router.add_route("*", "/api/quit", self._quit)
        app.router.add_route("*", "/api/show", self._show)
        app.router.add_route("*", "/api/probe", self._probe)
        app.router.add_route("*", "/api/probe-all", self._probe_all)
        app.router.add_route("*", "/api/reconnect", self._reconnect)
        app.router.add_route("*", "/api/relay/stop", self._relay_stop)
        app.router.add_route("*", "/api/relay/reconnect", self._relay_reconnect)
        app.router.add_route("*", "/api/autostart", self._autostart)
        # Discord bridge (Web 控制台调用)
        app.router.add_route("*", "/discord/status", self._discord_status)
        app.router.add_route("*", "/discord/token", self._discord_token)
        app.router.add_route("*", "/discord/validate", self._discord_validate)
        app.router.add_route("*", "/discord/guilds", self._discord_guilds)
        app.router.add_route("*", "/discord/guilds/{guild_id}/channels", self._discord_channels)
        app.router.add_route("*", "/discord/config", self._discord_config)
        app.router.add_route("*", "/discord/start", self._discord_start)
        app.router.add_route("*", "/discord/stop", self._discord_stop)
        app.router.add_route("*", "/discord/test-messages", self._discord_test_messages)
        if self._ui_root:
            app.router.add_get("/ui", self._ui_index_redirect)
            app.router.add_get("/ui/", self._ui_index)
            app.router.add_static("/ui/", str(self._ui_root), show_index=False)
        else:
            app.router.add_get("/ui/{path:.*}", self._ui_missing)
        return app

    async def start(self) -> None:
        if self._runner:
            return
        self._runner = web.AppRunner(self.build_app())
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, LOCAL_HOST, LOCAL_PORT)
        await self._site.start()
        if self._ui_root:
            logger.info("Agent UI http://%s:%s/ui/", LOCAL_HOST, LOCAL_PORT)
        else:
            logger.warning("Agent UI 未构建，请运行: cd clients/relay-agent/ui && npm install && npm run build")
        logger.info("Agent local API http://%s:%s", LOCAL_HOST, LOCAL_PORT)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def _health(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            return {
                "ok": True,
                "service": "sigtrades-agent",
                "ui": self._ui_root is not None,
                "version": self.version,
            }

        return await _json(request, h)

    async def _status(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            cfg = load_config()
            email = await self._fetch_email(cfg)
            from sigtrades_agent.idem_store import get_stats

            session_stats = self.state_holder.get("stats") or {}
            local_stats = get_stats()
            enabled_profiles = [p for p in cfg.broker_profiles if p.enabled]
            enabled_brokers = sorted({p.broker for p in enabled_profiles})
            # 优先用执行器真实 API 握手状态（TCP 通 ≠ IB/OpenD API 可用）
            if self._on_probe_all:
                gateways = await self._on_probe_all()
            else:
                gateways = probe_profiles(enabled_profiles, only_enabled=False)
            self.state_holder["gateways"] = gateways
            brokers_agg: dict[str, bool] = {b: False for b in enabled_brokers}
            for row in gateways:
                b = str(row.get("broker") or "")
                if b:
                    brokers_agg[b] = brokers_agg.get(b, False) or bool(row.get("online"))
            self.state_holder["brokers"] = brokers_agg
            relay_held = bool(self._relay_held_getter()) if self._relay_held_getter else False
            return {
                "online": bool(self.state_holder.get("online")),
                "relay_held": relay_held,
                "brokers": brokers_agg,
                "gateways": gateways,
                "device_id": cfg.device_id,
                "relay_url": cfg.relay_url,
                "logged_in": bool(cfg.user_token),
                "email": email,
                "language": cfg.language,
                "version": self.version,
                "ui_available": self._ui_root is not None,
                "enabled_brokers": enabled_brokers,
                "stats": {
                    "session_received": int(session_stats.get("session_received", 0)),
                    "session_failed": int(session_stats.get("session_failed", 0)),
                    **local_stats,
                },
            }

        return await _json(request, h)

    async def _config(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method == "GET":
                cfg = load_config()
                return {
                    "language": cfg.language,
                    "relay_url": cfg.relay_url,
                    "broker_profiles": [asdict(p) for p in cfg.broker_profiles],
                }
            if req.method != "PATCH":
                raise ValueError("GET or PATCH required")
            body = await req.json()
            cfg = load_config()
            if "language" in body:
                cfg.language = str(body["language"])[:8] or "zh"
            if "relay_url" in body and str(body["relay_url"]).strip():
                cfg.relay_url = str(body["relay_url"]).strip()
            if "broker_profiles" in body:
                cfg.broker_profiles = [
                    BrokerProfile(**item) for item in (body["broker_profiles"] or [])
                ]
            save_config(cfg)
            applied: dict[str, Any] = {"restart_required": False}
            if self._on_config_apply:
                applied = await self._on_config_apply(cfg) or applied
            return {"ok": True, **applied}

        return await _json(request, h)

    async def _login(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if not self._on_login:
                raise ValueError("login not available")
            result = self._on_login()
            if inspect.isawaitable(result):
                cfg = await result
            else:
                cfg = result
            email = await self._fetch_email(cfg)
            return {"ok": True, "email": email}

        return await _json(request, h)

    async def _logout(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            cfg = load_config()
            cfg.user_token = ""
            cfg.account_email = ""
            save_config(cfg)
            if self._on_logout:
                self._on_logout()
            return {"ok": True}

        return await _json(request, h)

    async def _quit(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if self._on_quit:
                # 延迟一拍，先把 HTTP 响应发出去
                import asyncio

                asyncio.get_running_loop().call_later(0.15, self._on_quit)
            return {"ok": True}

        return await _json(request, h)

    async def _show(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method not in {"GET", "POST"}:
                raise ValueError("GET or POST required")
            if self._on_show:
                self._on_show()
            return {"ok": True}

        return await _json(request, h)

    async def _probe(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            body = await req.json()
            broker = str(body.get("broker") or "").strip()
            if broker not in {"ibkr", "futu"}:
                raise ValueError("broker must be ibkr or futu")
            ok = probe_broker(broker, body.get("config") or {})
            return {"ok": ok, "broker": broker}

        return await _json(request, h)

    async def _probe_all(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if self._on_probe_all:
                gateways = await self._on_probe_all()
            else:
                cfg = load_config()
                gateways = probe_profiles(cfg.broker_profiles, only_enabled=True)
            self.state_holder["gateways"] = gateways
            brokers: dict[str, bool] = {}
            for row in gateways:
                b = str(row.get("broker") or "")
                if b:
                    brokers[b] = brokers.get(b, False) or bool(row.get("online"))
            self.state_holder["brokers"] = brokers
            online_n = sum(1 for g in gateways if g.get("online"))
            return {"ok": True, "gateways": gateways, "online": online_n, "total": len(gateways)}

        return await _json(request, h)

    async def _reconnect(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if not self._on_reconnect:
                raise ValueError("reconnect not available")
            body = await req.json()
            broker = str(body.get("broker") or "").strip()
            account_id = str(body.get("account_id") or "").strip()
            if broker not in {"ibkr", "futu"}:
                raise ValueError("broker must be ibkr or futu")
            if not account_id:
                raise ValueError("account_id required")
            return await self._on_reconnect(broker, account_id)

        return await _json(request, h)

    async def _relay_stop(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if not self._on_relay_stop:
                raise ValueError("relay stop not available")
            return await self._on_relay_stop()

        return await _json(request, h)

    async def _relay_reconnect(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            if not self._on_relay_reconnect:
                raise ValueError("relay reconnect not available")
            return await self._on_relay_reconnect()

        return await _json(request, h)

    async def _autostart(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            from sigtrades_agent.autostart import autostart_installed, install_autostart, uninstall_autostart

            if req.method == "GET":
                return {"enabled": autostart_installed()}
            if req.method != "POST":
                raise ValueError("GET or POST required")
            body = await req.json()
            enabled = bool(body.get("enabled"))
            if enabled:
                install_autostart()
            else:
                uninstall_autostart()
            return {"enabled": autostart_installed()}

        return await _json(request, h)

    async def _ui_index_redirect(self, _: web.Request) -> web.Response:
        raise web.HTTPFound("/ui/")

    async def _ui_index(self, _: web.Request) -> web.Response:
        return web.FileResponse(self._ui_root / "index.html")

    async def _ui_missing(self, _: web.Request) -> web.Response:
        return web.Response(
            text="Agent UI not built. Run: cd clients/relay-agent/ui && npm install && npm run build",
            status=503,
        )

    async def _fetch_email(self, cfg: AgentConfig) -> str | None:
        if cfg.account_email:
            return cfg.account_email
        if not cfg.user_token:
            return None
        import os

        import httpx

        from sigtrades_agent.cloud_defaults import DEFAULT_API_URL

        base = os.getenv("SIGTRADES_API_URL", DEFAULT_API_URL).rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
                r = await client.post(
                    f"{base}/public/agent/me",
                    json={"user_token": cfg.user_token},
                )
                if r.status_code == 200:
                    email = r.json().get("email")
                    if email:
                        cfg.account_email = email
                        save_config(cfg)
                    return email
        except Exception as e:  # noqa: BLE001
            logger.debug("fetch email failed: %s", e)
        return None

    # Discord handlers (same as discord_local_api)
    async def _discord_status(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            return self.bridge.state.status_dict()

        return await _json(request, h)

    async def _discord_token(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            body = await req.json()
            token = (body.get("token") or "").strip()
            if len(token) < 50:
                raise ValueError("invalid token")
            self.bridge.set_token(token)
            user = await self.bridge.validate_token()
            return {"ok": True, "user": user}

        return await _json(request, h)

    async def _discord_validate(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            user = await self.bridge.validate_token()
            return {"ok": True, "user": user}

        return await _json(request, h)

    async def _discord_guilds(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            guilds = await self.bridge.fetch_guilds()
            return {"guilds": guilds}

        return await _json(request, h)

    async def _discord_channels(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            guild_id = req.match_info["guild_id"]
            channels = await self.bridge.fetch_guild_channels(guild_id)
            return {"channels": channels}

        return await _json(request, h)

    async def _discord_config(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            if req.method != "POST":
                raise ValueError("POST required")
            body = await req.json()
            self.bridge.configure(
                channel_ids=body.get("channel_ids") or [],
                channel_labels=body.get("channel_labels") or {},
                webhook_url=body.get("webhook_url") or "",
            )
            return {"ok": True, **self.bridge.state.status_dict()}

        return await _json(request, h)

    async def _discord_start(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            await self.bridge.start()
            return {"ok": True, "running": True}

        return await _json(request, h)

    async def _discord_stop(self, request: web.Request) -> web.Response:
        async def h(_: web.Request) -> dict[str, Any]:
            await self.bridge.stop()
            return {"ok": True, "running": False}

        return await _json(request, h)

    async def _discord_test_messages(self, request: web.Request) -> web.Response:
        async def h(req: web.Request) -> dict[str, Any]:
            limit = int(req.query.get("limit", "20"))
            return {"messages": self.bridge.get_test_messages(limit)}

        return await _json(request, h)


# 兼容旧 import
DiscordLocalApi = AgentLocalApi
