"""Agent 反向 WS 客户端：注册 + 心跳 + 重连 + 信号分发 + 回执上报。

线程模型：
- WS 主循环跑在 asyncio 事件循环（主线程）。
- 每个券商执行器跑在自己的线程（IBKR 事件循环线程 / 富途 worker）。
- 执行器回执通过线程安全方式投回 asyncio 循环再经 WS 上行。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from typing import Dict, List, Optional
from urllib.parse import urlparse

import websockets

from sigtrades_protocol import (
    MessageType,
    AgentRegister,
    AgentHeartbeat,
    AgentStatus,
    ExecutionReport,
    Ack,
    ProbeAccountResult,
    decode_message,
    encode_message,
)
from sigtrades_core.execution.core import ExecutionReportData

from sigtrades_agent.config import AgentConfig
from sigtrades_agent.executors import get_executor_class
from sigtrades_agent.executors.base import BrokerExecutor

logger = logging.getLogger(__name__)


def _connect_kwargs(relay_url: str) -> dict:
    """本机 relay 不走系统代理，避免 SOCKS/HTTP proxy 导致 localhost 连接失败。"""
    host = (urlparse(relay_url).hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return {"proxy": None}
    return {}


class RelayAgent:
    def __init__(self, config: AgentConfig, on_state=None, stats: Optional[dict] = None):
        self.config = config
        self._on_state = on_state  # 可选：托盘状态回调 (online: bool, brokers: dict)
        self._stats = stats if stats is not None else {}
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # broker -> [executors]，支持同一券商多 gateway profile
        self._executors: Dict[str, List[BrokerExecutor]] = {}
        self._paused = False
        self._stop = asyncio.Event()
        self._connected = False
        # True 时断开 relay 且不自动重连（UI「停止」）；「重连」清除后恢复
        self._relay_hold = False

    # ------------------------------------------------------------------
    # 执行器
    # ------------------------------------------------------------------
    def _start_executors(self) -> None:
        for profile in self.config.broker_profiles:
            if not profile.enabled:
                continue
            cls = get_executor_class(profile.broker)
            if cls is None:
                logger.warning("无可用执行器: %s（缺少 SDK 或未实现）", profile.broker)
                continue
            ex = cls(profile, report_sink=self._on_report, paused_flag=lambda: self._paused)
            ex.start()
            self._executors.setdefault(profile.broker, []).append(ex)
            logger.info("启动执行器: %s profile=%s", profile.broker, profile.key)

    def _stop_executors(self) -> None:
        for ex in self._all_executors():
            with contextlib.suppress(Exception):
                ex.stop()
        self._executors.clear()

    def _all_executors(self) -> List[BrokerExecutor]:
        return [ex for lst in self._executors.values() for ex in lst]

    def _find_executor(self, broker: str, account_id: Optional[str]) -> Optional[BrokerExecutor]:
        """按券商找执行器；账户号由网页下发，在执行时写入 adapter，不按 Agent 本地 account_id 匹配。"""
        lst = self._executors.get(broker, [])
        if not lst:
            return None
        if account_id:
            for ex in lst:
                if ex.account_id and ex.account_id == account_id:
                    return ex
        return lst[0]  # 单连接 profile：取第一个，用消息里的 account_id 下单

    async def apply_config(self, cfg: AgentConfig) -> dict:
        """保存后热加载：重载券商执行器；capabilities / relay 变更时强制重连注册。"""
        old_caps = set(self.config.capabilities)
        old_relay = self.config.relay_url
        self.config.language = cfg.language or self.config.language
        if cfg.relay_url:
            self.config.relay_url = cfg.relay_url
        self._stop_executors()
        self.config.broker_profiles = list(cfg.broker_profiles or [])
        self._start_executors()
        new_caps = set(self.config.capabilities)
        need_reconnect = (old_caps != new_caps) or (old_relay != self.config.relay_url)
        if need_reconnect and self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.close()
            logger.info("配置变更，已触发 relay 重连以刷新 capabilities")
        # 给执行器一点时间尝试连接，再批量探测并刷新首页状态
        await asyncio.sleep(0.4)
        await self.refresh_gateway_status()
        return {"restart_required": False, "reconnected": need_reconnect}

    async def refresh_gateway_status(self) -> List[dict]:
        """并行探测全部已启用连接，更新 state 并（若已连 relay）上报 AgentStatus。"""
        loop = asyncio.get_running_loop()
        gateways = await loop.run_in_executor(None, self._gateway_rows)
        brokers: Dict[str, bool] = {}
        for row in gateways:
            brokers[row["broker"]] = brokers.get(row["broker"], False) or bool(row["online"])
        for b in self.config.capabilities:
            brokers.setdefault(b, False)
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._send(
                    encode_message(
                        AgentStatus(
                            device_id=self.config.device_id, brokers=brokers, gateways=gateways
                        )
                    )
                )
        if self._on_state:
            self._on_state(self._connected, brokers, gateways)
        return gateways

    async def reconnect_profile(self, broker: str, account_id: str) -> dict:
        """重启指定连接模式的执行器并探测是否在线。"""
        account_id = (account_id or "").strip()
        profile = next(
            (
                p
                for p in self.config.broker_profiles
                if p.broker == broker and (p.account_id or "") == account_id and p.enabled
            ),
            None,
        )
        if profile is None:
            return {"ok": False, "online": False, "error": "profile not found or disabled"}

        lst = self._executors.setdefault(broker, [])
        existing = None
        for i, ex in enumerate(list(lst)):
            if (getattr(ex.profile, "account_id", "") or "") == account_id:
                existing = ex
                lst.pop(i)
                break

        if existing is not None:
            with contextlib.suppress(Exception):
                existing.stop()
                existing.join(timeout=3.0)

        cls = get_executor_class(broker)
        if cls is None:
            return {"ok": False, "online": False, "error": f"no executor for {broker}"}
        ex = cls(profile, report_sink=self._on_report, paused_flag=lambda: self._paused)
        ex.start()
        lst.append(ex)
        logger.info("重连执行器: %s profile=%s", broker, profile.key)

        # 等待线程内 connect 完成
        await asyncio.sleep(0.8)
        loop = asyncio.get_running_loop()

        def _wait_connected() -> bool:
            deadline = time.time() + 12.0
            while time.time() < deadline:
                if ex.is_connected():
                    return True
                time.sleep(0.25)
            # 不再用 TCP 端口探测冒充成功（端口开 ≠ IB API 可用）
            return bool(ex.is_connected())

        online = await loop.run_in_executor(None, _wait_connected)
        await self.refresh_gateway_status()
        error = None
        if not online:
            # 优先执行器内真实错误（如打包缺 numpy），避免误报成 TWS 握手失败
            detail = (getattr(ex, "_last_connect_error", None) or "").strip()
            if detail and any(
                k in detail.lower()
                for k in (
                    "no module named",
                    "cannot import",
                    "导入失败",
                    "import",
                    "模块未安装",
                )
            ):
                error = f"Agent 本地组件异常: {detail}（请重新安装/更新 Agent）"
            else:
                from sigtrades_agent.gateway_probe import diagnose_broker

                diag = await loop.run_in_executor(
                    None, lambda: diagnose_broker(broker, profile.config or {})
                )
                if diag.get("ok"):
                    host = diag.get("host") or "127.0.0.1"
                    port = diag.get("port") or ""
                    suffix = f" 详情: {detail}" if detail else ""
                    if broker == "futu":
                        error = (
                            f"{host}:{port} 端口可连，但 OpenD API 握手失败。"
                            "请确认 OpenD 已登录且 API 已开启，重启 OpenD 后点重连。"
                            f"{suffix}"
                        )
                    else:
                        error = (
                            f"{host}:{port} 端口可连，但 IB API 握手失败。"
                            "请在 TWS 启用 API 并点 Accept；完全重启后再点重连；"
                            "仍失败可暂时关闭 Clash/系统代理。"
                            f"{suffix}"
                        )
                else:
                    error = diag.get("error") or detail or "broker gateway offline"
        return {
            "ok": online,
            "online": online,
            "broker": broker,
            "account_id": account_id,
            "name": profile.name or account_id or broker,
            "error": error,
        }

    def _close_ws_soon(self) -> None:
        """在事件循环上异步关闭当前 relay WS（可从任意线程调用）。"""
        ws = self._ws
        loop = self._loop
        if ws is None or loop is None or not loop.is_running():
            return

        async def _close() -> None:
            with contextlib.suppress(Exception):
                await ws.close()

        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            with contextlib.suppress(Exception):
                loop.create_task(_close())
        else:
            with contextlib.suppress(Exception):
                asyncio.run_coroutine_threadsafe(_close(), loop)

    def reconnect_after_login(self) -> None:
        """登录成功后允许 WS 重连循环继续运行。"""
        self._relay_hold = False
        self._stop.clear()
        # 若仍挂着旧 socket，先关掉，促使 run() 用新 token 重新注册
        self._close_ws_soon()

    def disconnect_cloud(self) -> None:
        """退出登录：断开 relay / 停重连循环，保留本地券商执行器。"""
        self._stop.set()
        self._relay_hold = False
        self._close_ws_soon()
        self._set_online(False)
        logger.info("已断开云端 relay（保留本地券商连接）")

    async def reconnect_all_profiles(self, *, only_offline: bool = True) -> dict:
        """登录后重试券商连接。默认只重连当前离线的已启用 profile。"""
        if not self._executors:
            self._start_executors()
            await asyncio.sleep(0.5)

        gateways = await self.refresh_gateway_status()
        online_keys = {
            (str(g.get("broker") or ""), str(g.get("account_id") or ""))
            for g in gateways
            if g.get("online")
        }
        results: List[dict] = []
        for profile in self.config.broker_profiles:
            if not profile.enabled:
                continue
            key = (profile.broker, profile.account_id or "")
            if only_offline and key in online_keys:
                results.append(
                    {
                        "ok": True,
                        "online": True,
                        "broker": profile.broker,
                        "account_id": profile.account_id or "",
                        "skipped": True,
                    }
                )
                continue
            results.append(
                await self.reconnect_profile(profile.broker, profile.account_id or "")
            )

        gateways = await self.refresh_gateway_status()
        online_n = sum(1 for g in gateways if g.get("online"))
        return {
            "ok": True,
            "online": online_n,
            "total": len(gateways),
            "results": results,
            "gateways": gateways,
        }

    async def stop_relay(self) -> dict:
        """断开与服务端的 relay 连接，并暂停自动重连。"""
        self._relay_hold = True
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
        self._set_online(False)
        logger.info("已停止 relay 连接（保持本地执行器）")
        return {"ok": True, "online": False, "relay_held": True}

    async def reconnect_relay(self) -> dict:
        """恢复 / 强制重连服务端 relay。"""
        self._relay_hold = False
        self._stop.clear()
        ws = self._ws
        if ws is not None:
            with contextlib.suppress(Exception):
                await ws.close()
            logger.info("已触发 relay 重连")
        else:
            logger.info("已解除 relay 暂停，等待连接循环恢复")
        # 稍等连接建立，便于 UI 立刻看到状态
        for _ in range(20):
            await asyncio.sleep(0.25)
            if self._connected and not self._relay_hold:
                break
        return {
            "ok": bool(self._connected),
            "online": bool(self._connected),
            "relay_held": bool(self._relay_hold),
        }

    def _gateway_rows(self) -> List[dict]:
        """各连接模式状态（与本机 Agent UI 一致）。

        「在线」= 执行器已真正完成券商 API 握手；仅端口 LISTEN/TCP 通不算在线，
        避免首页显示在线但网页「测试账户」仍失败。
        """
        from sigtrades_agent.gateway_probe import probe_profiles

        rows = probe_profiles(self.config.broker_profiles, only_enabled=True)
        connected: Dict[str, bool] = {}
        warnings: Dict[str, str] = {}
        for ex in self._all_executors():
            key = f"{ex.broker}:{getattr(ex.profile, 'account_id', '') or ''}"
            connected[key] = bool(ex.is_connected())
            adapter = getattr(ex, "_adapter", None)
            warn = getattr(adapter, "opend_version_warning", None) if adapter else None
            if isinstance(warn, str) and warn.strip():
                warnings[key] = warn.strip()
        for row in rows:
            key = f"{row['broker']}:{row.get('account_id') or ''}"
            row["port_open"] = bool(row.get("online"))
            row["online"] = bool(connected.get(key))
            if key in warnings:
                row["warning"] = warnings[key]
        return rows

    def _broker_status(self) -> Dict[str, bool]:
        """回报各券商是否可用（任一 profile 在线即为 True）。"""
        status: Dict[str, bool] = {}
        for row in self._gateway_rows():
            broker = row["broker"]
            status[broker] = status.get(broker, False) or bool(row["online"])
        for b in self.config.capabilities:
            status.setdefault(b, False)
        return status

    # ------------------------------------------------------------------
    # 执行器回执 -> WS（线程安全）
    # ------------------------------------------------------------------
    def _on_report(self, rpt: ExecutionReportData) -> None:
        if self._loop is None:
            return
        msg = ExecutionReport(**rpt.to_dict())
        asyncio.run_coroutine_threadsafe(self._send(encode_message(msg)), self._loop)

    async def _send(self, text: str) -> None:
        if self._ws is not None:
            with contextlib.suppress(Exception):
                await self._ws.send(text)

    # ------------------------------------------------------------------
    # 主运行循环（含重连退避）
    # ------------------------------------------------------------------
    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        # 若 UI 已热加载过配置，执行器可能已在跑，避免重复启动
        if not self._executors:
            self._start_executors()
        backoff = self.config.reconnect_min
        while not self._stop.is_set():
            if self._relay_hold:
                self._set_online(False)
                await asyncio.sleep(0.5)
                continue
            try:
                await self._connect_once()
                backoff = self.config.reconnect_min
            except Exception as e:  # noqa: BLE001
                self._set_online(False)
                if self._relay_hold:
                    continue
                logger.warning("连接断开: %s，%.1fs 后重连", e, backoff)
                await asyncio.sleep(backoff)
                backoff = min(self.config.reconnect_max, backoff * 2)

    async def _connect_once(self) -> None:
        logger.info("连接 relay: %s", self.config.relay_url)
        async with websockets.connect(
            self.config.relay_url,
            max_size=2**20,
            **_connect_kwargs(self.config.relay_url),
        ) as ws:
            self._ws = ws
            # 注册
            reg = AgentRegister(
                user_token=self.config.user_token,
                device_id=self.config.device_id,
                capabilities=self.config.capabilities,
                platform=__import__("sys").platform,
            )
            await ws.send(encode_message(reg))
            ack_raw = await ws.recv()
            ack = decode_message(ack_raw)
            if not (isinstance(ack, Ack) and ack.ok):
                msg = getattr(ack, "message", "") or ""
                if msg == "session_displaced":
                    logger.error("Agent 已在其他设备登录: %s", msg)
                    self._stop.set()
                elif msg == "认证失败":
                    logger.error("Agent 会话已失效，请重新登录: %s", msg)
                raise RuntimeError(f"注册失败: {msg}")
            logger.info("注册成功 device=%s", self.config.device_id)
            self._set_online(True)

            await self._send_status()
            hb_task = asyncio.create_task(self._heartbeat_loop())
            try:
                async for raw in ws:
                    await self._handle_downstream(raw)
            finally:
                hb_task.cancel()
                self._set_online(False)
                self._ws = None

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            await self._send(encode_message(
                AgentHeartbeat(device_id=self.config.device_id, ts=time.time())
            ))

    async def _send_status(self) -> None:
        await self.refresh_gateway_status()

    async def _handle_downstream(self, raw) -> None:
        try:
            msg = decode_message(raw)
        except Exception as e:  # noqa: BLE001
            logger.warning("无法解析下行消息: %s", e)
            return

        if msg.type == MessageType.EXECUTE_SIGNAL:
            await self._dispatch_execute(msg)
        elif msg.type == MessageType.CANCEL_SIGNAL:
            logger.info("收到撤单指令: %s", msg.signal_id)
            # 撤单转交对应执行器（按 broker 暂略，执行器内已自带超时撤单）
        elif msg.type == MessageType.PAUSE_AGENT:
            self._paused = bool(msg.paused)
            logger.info("急停状态: paused=%s reason=%s", self._paused, msg.reason)
        elif msg.type == MessageType.PROBE_ACCOUNT:
            await self._dispatch_probe(msg)
        elif msg.type == MessageType.ACK:
            pass

    async def _dispatch_probe(self, msg) -> None:
        broker = str(getattr(msg, "broker", "") or "")
        account_id = getattr(msg, "account_id", None)
        request_id = str(getattr(msg, "request_id", "") or "")
        ex = self._find_executor(broker, account_id)
        if ex is None:
            await self._send(
                encode_message(
                    ProbeAccountResult(
                        request_id=request_id,
                        ok=False,
                        broker=broker,
                        account_id=account_id,
                        error=f"无 {broker} 执行器",
                        device_id=self.config.device_id,
                    )
                )
            )
            return

        try:
            fut = ex.submit_probe()
            result = await asyncio.get_running_loop().run_in_executor(
                None, lambda: fut.result(timeout=20.0)
            )
        except Exception as e:  # noqa: BLE001
            # concurrent.futures.TimeoutError / asyncio.TimeoutError 的 str() 常为空
            err = (str(e) or "").strip()
            if not err or type(e).__name__ in {"TimeoutError", "CancelledError"}:
                err = (
                    "账户探测超时：TWS API 无响应。"
                    "请在 Agent 对该模式点重连，或重启 TWS 后再测"
                )
            result = {
                "ok": False,
                "broker": broker,
                "account_id": account_id,
                "account_summary": None,
                "error": err,
            }
        await self._send(
            encode_message(
                ProbeAccountResult(
                    request_id=request_id,
                    ok=bool(result.get("ok")),
                    broker=str(result.get("broker") or broker),
                    account_id=result.get("account_id") or account_id,
                    account_summary=result.get("account_summary"),
                    error=result.get("error"),
                    device_id=self.config.device_id,
                )
            )
        )

    def _bump_stat(self, key: str, amount: int = 1) -> None:
        self._stats[key] = int(self._stats.get(key, 0)) + amount

    async def _dispatch_execute(self, msg) -> None:
        broker = msg.broker
        self._bump_stat("session_received")
        ex = self._find_executor(broker, msg.account_id)
        if ex is None:
            self._bump_stat("session_failed")
            rpt = ExecutionReport(
                signal_id=msg.signal_id, source_id=msg.source_id, broker=broker,
                account_id=msg.account_id, status="FAILED", error=f"无 {broker} 执行器",
            )
            await self._send(encode_message(rpt))
            return
        # 确认收到
        await self._send(encode_message(Ack(ref_type="execute_signal", signal_id=msg.signal_id, ok=True)))
        ex.submit(msg.model_dump())

    def _set_online(self, online: bool) -> None:
        self._connected = online
        if self._on_state:
            with contextlib.suppress(Exception):
                # 勿在此同步调用 _broker_status()：富途/IBKR connect 失败重试会堵死
                # 主事件循环，导致本机 API(:17890) 与桌面 UI 无响应。
                brokers: Dict[str, bool] = {}
                if online:
                    for ex in self._all_executors():
                        brokers[ex.broker] = brokers.get(ex.broker, False) or ex.is_connected()
                try:
                    self._on_state(online, brokers, None)
                except TypeError:
                    self._on_state(online, brokers)

    def stop(self) -> None:
        """完整停止：relay + 全部本地执行器（用于退出 App）。"""
        self._stop.set()
        self._relay_hold = False
        self._close_ws_soon()
        self._set_online(False)
        self._stop_executors()
