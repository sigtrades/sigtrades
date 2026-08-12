"""券商执行器基类：每个本地券商在自己的线程里跑，承载 ExecutionCore。

- IBKR：专属事件循环线程（ib_async 单线程事件循环约束）。
- 富途：普通 worker 线程。
两者都用「线程 + 任务队列」模型，由本基类统一：注册/连接/幂等/回执。
"""

from __future__ import annotations

import contextlib
import logging
import queue
import threading
import time
from concurrent.futures import Future
from typing import Any, Callable, Dict, Optional, Tuple

from sigtrades_core.signal.models import Signal
from sigtrades_core.execution.core import ExecutionCore, ExecutionReportData
from sigtrades_core.brokers.base import BaseBrokerAdapter
from sigtrades_agent.idem_store import get_terminal, save_terminal

logger = logging.getLogger(__name__)

ReportSink = Callable[[ExecutionReportData], None]


class BrokerExecutor(threading.Thread):
    """单券商执行线程。"""

    broker: str = "generic"

    def __init__(self, profile, report_sink: ReportSink, paused_flag: Callable[[], bool]):
        super().__init__(daemon=True, name=f"executor-{self.broker}")
        self.profile = profile
        self.account_id = getattr(profile, "account_id", "") or None
        self._report_sink = report_sink
        self._is_paused = paused_flag
        self._adapter: Optional[BaseBrokerAdapter] = None
        self._connected = False
        self._last_connect_error: Optional[str] = None
        self._tasks: "queue.Queue[Optional[Tuple[str, dict]]]" = queue.Queue()
        self._stop = threading.Event()
        # 幂等：(source_id, signal_id, account_id) -> 最终回执
        self._idem: Dict[Tuple[str, str, Optional[str]], ExecutionReportData] = {}
        self._idem_lock = threading.Lock()

    # ---- 子类实现 ----
    def _create_adapter(self) -> BaseBrokerAdapter:
        raise NotImplementedError

    def _thread_setup(self) -> None:
        """线程启动时的一次性准备（IBKR 子类在此创建专属事件循环）。"""
        return None

    def _run_in_thread(self, fn: Callable[[], Any]) -> Any:
        """在本执行器所属线程上下文执行。

        基类即「单线程」模型：run() / connect / execute 全在本线程，天然满足
        IBKR ib_async 单线程事件循环约束，故直接调用即可。
        """
        return fn()

    # ---- 公共能力 ----
    def is_connected(self) -> bool:
        return self._connected

    def submit(self, execute_msg: dict) -> None:
        """投递一条 execute_signal（dict 形式）。"""
        self._tasks.put(("execute", execute_msg))

    def submit_probe(self) -> "Future[Dict[str, Any]]":
        """在执行器线程内探测账户（IBKR 需同线程事件循环）。"""
        fut: Future[Dict[str, Any]] = Future()
        self._tasks.put(("probe", fut))
        return fut

    def submit_reconnect(self) -> "Future[bool]":
        """在执行器线程内强制断开并重连网关。"""
        fut: Future[bool] = Future()
        self._tasks.put(("reconnect", fut))
        return fut

    def stop(self) -> None:
        self._stop.set()
        self._tasks.put(None)

    def _cleanup_adapter(self) -> None:
        """线程退出前断开券商连接，释放 IB clientId 等资源。"""
        if self._adapter is not None:
            with contextlib.suppress(Exception):
                self._run_in_thread(self._adapter.disconnect)
        self._adapter = None
        self._connected = False

    # ---- 线程主循环 ----
    def run(self) -> None:
        self._thread_setup()
        try:
            self._ensure_connected()
            while not self._stop.is_set():
                try:
                    item = self._tasks.get(timeout=1.0)
                except queue.Empty:
                    continue
                if item is None:
                    break
                kind, payload = item
                if kind == "execute":
                    self._do_execute(payload)
                elif kind == "probe":
                    fut: Future = payload
                    try:
                        fut.set_result(self.probe_account())
                    except Exception as e:  # noqa: BLE001
                        fut.set_exception(e)
                elif kind == "reconnect":
                    fut: Future = payload
                    try:
                        fut.set_result(self._force_reconnect())
                    except Exception as e:  # noqa: BLE001
                        fut.set_exception(e)
        finally:
            self._cleanup_adapter()

    def _ensure_connected(self) -> bool:
        if self._connected and self._adapter is not None:
            return True
        try:
            self._adapter = self._create_adapter()
            ok = bool(self._run_in_thread(self._adapter.connect))
            self._connected = ok
            if ok:
                self._last_connect_error = None
                logger.info("[%s] 网关已连接", self.broker)
            else:
                self._last_connect_error = self._last_connect_error or "券商 connect() 返回失败"
                logger.warning("[%s] 网关连接失败", self.broker)
            return ok
        except Exception as e:  # noqa: BLE001
            self._last_connect_error = str(e) or type(e).__name__
            logger.error("[%s] 连接异常: %s", self.broker, e)
            self._connected = False
            return False

    def _force_reconnect(self) -> bool:
        """断开现有连接并重新 connect。"""
        if self._adapter is not None:
            with contextlib.suppress(Exception):
                self._run_in_thread(self._adapter.disconnect)
        self._adapter = None
        self._connected = False
        self._last_connect_error = None
        return self._ensure_connected()

    def broker_status(self) -> bool:
        return self._ensure_connected()

    def _gateway_offline_error(self) -> str:
        """连接失败时尽量给出可操作诊断（依赖缺失 / 端口未开 / TCP 通但 API 握手失败）。"""
        detail = (self._last_connect_error or "").strip()
        # 打包缺失依赖等：不要误报成「TWS 握手失败」
        if detail and any(
            k in detail.lower()
            for k in ("no module named", "cannot import", "模块未安装", "import")
        ):
            return f"Agent 本地组件异常: {detail}（请重新安装/更新 Agent）"
        try:
            from sigtrades_agent.gateway_probe import diagnose_broker

            cfg = getattr(self.profile, "config", None) or {}
            diag = diagnose_broker(self.broker, cfg)
            # TCP 已通但执行器仍连不上 → 典型「Accept / 代理 / API 未真正就绪」
            if diag.get("ok"):
                host = diag.get("host") or cfg.get("host") or "127.0.0.1"
                port = diag.get("port") or cfg.get("port") or ""
                suffix = f" 详情: {detail}" if detail else ""
                if self.broker == "ibkr":
                    return (
                        f"{host}:{port} 端口可连，但券商 API 握手失败。"
                        "请在 TWS：启用 Socket API、确认端口、弹窗点 Allow/Accept；"
                        "完全退出并重启 TWS 后点重连；仍失败可暂时关闭 Clash/系统代理。"
                        f"{suffix}"
                    )
                return (
                    f"{host}:{port} 端口可连，但券商 API 握手失败。"
                    "请确认 OpenD 已登录且 API 已开启，重启 OpenD 后点重连。"
                    f"{suffix}"
                )
            if diag.get("error"):
                err = str(diag["error"])
                return f"{err} 详情: {detail}" if detail else err
        except Exception:  # noqa: BLE001
            pass
        return detail or "broker gateway offline"

    def probe_account(self) -> Dict[str, Any]:
        """探测网关连通性并尽量拉取账户摘要（供网页「测试账户」）。"""
        from sigtrades_core.brokers.account_probe import normalize_account_summary

        if not self._ensure_connected() or self._adapter is None:
            return {
                "ok": False,
                "broker": self.broker,
                "account_id": self.account_id,
                "account_summary": None,
                "error": self._gateway_offline_error(),
            }
        try:
            info = self._run_in_thread(self._adapter.get_account_info)
            summary = normalize_account_summary(self.broker, info if isinstance(info, dict) else {})
            # 连接上但净值/可用都空：不算测通（避免网页只显示「连通成功」却无数据）
            if summary.get("net_liquidation") is None and summary.get("available_cash") is None:
                return {
                    "ok": False,
                    "broker": self.broker,
                    "account_id": self.account_id or summary.get("account_id"),
                    "account_summary": summary,
                    "error": "已连接，但未返回净值/可用资金（请确认账户已登录且 API 权限正常）",
                }
            warning = getattr(self._adapter, "opend_version_warning", None)
            return {
                "ok": True,
                "broker": self.broker,
                "account_id": self.account_id or summary.get("account_id"),
                "account_summary": summary,
                "error": None,
                "warning": warning if isinstance(warning, str) and warning.strip() else None,
                "opend_server_ver": getattr(self._adapter, "opend_server_ver", None),
            }
        except Exception as e:  # noqa: BLE001
            logger.warning("[%s] probe_account failed: %s", self.broker, e)
            return {
                "ok": False,
                "broker": self.broker,
                "account_id": self.account_id,
                "account_summary": None,
                "error": str(e),
            }

    def _runtime_account_id(self, msg: dict) -> Optional[str]:
        """优先用网页下发的 account_id（含 IBKR 连接模式 id）；未指定则回退 profile。"""
        raw = msg.get("account_id")
        if raw is not None and str(raw).strip():
            return str(raw).strip()
        return self.account_id

    @staticmethod
    def _is_connection_preset(broker: str, account_id: Optional[str]) -> bool:
        """网页绑定用的连接模式 id，只用于路由，不是券商真实账户号。"""
        if not account_id:
            return False
        try:
            if broker == "ibkr":
                from sigtrades_agent.ibkr_presets import IBKR_PRESETS

                return account_id in {row[0] for row in IBKR_PRESETS}
            if broker == "futu":
                from sigtrades_agent.futu_presets import FUTU_PRESETS

                return account_id in {row[0] for row in FUTU_PRESETS}
        except Exception:  # noqa: BLE001
            pass
        return account_id in {
            "tws-paper",
            "tws-live",
            "gateway-live",  # 历史绑定 id，仍视为连接模式而非真实账户
            "gateway-paper",
            "futu-simulate",
            "futu-real",
        }

    def _apply_runtime_account(self, account_id: Optional[str]) -> None:
        """把真实交易账户写入 adapter。连接模式 id 只用于路由，不写入。"""
        if not account_id or self._adapter is None:
            return
        if self._is_connection_preset(self.broker, account_id):
            return
        if hasattr(self._adapter, "account"):
            self._adapter.account = account_id
        if hasattr(self._adapter, "acc_id"):
            try:
                self._adapter.acc_id = int(account_id)
            except (TypeError, ValueError):
                pass

    def _do_execute(self, msg: dict) -> None:
        signal_id = msg.get("signal_id", "")
        source_id = msg.get("source_id", "")
        account_id = self._runtime_account_id(msg)
        key = (source_id, signal_id, account_id)

        cached_payload = get_terminal(source_id, signal_id, account_id)
        if cached_payload is not None:
            logger.info("[%s] SQLite 幂等命中 %s/%s", self.broker, source_id, signal_id)
            fields = {f: cached_payload[f] for f in ExecutionReportData.__dataclass_fields__ if f in cached_payload}
            self._report_sink(ExecutionReportData(**fields))
            return

        with self._idem_lock:
            cached = self._idem.get(key)
        if cached is not None:
            logger.info("[%s] 幂等命中，跳过重复信号 %s/%s", self.broker, source_id, signal_id)
            cached.error = (cached.error or "") + " (dedup)"
            self._report_sink(cached)
            return

        if self._is_paused():
            rpt = ExecutionReportData(
                signal_id=signal_id, source_id=source_id, broker=self.broker,
                account_id=account_id, status="SKIPPED", error="agent paused",
            )
            self._report_sink(rpt)
            return

        if not self._ensure_connected():
            rpt = ExecutionReportData(
                signal_id=signal_id, source_id=source_id, broker=self.broker,
                account_id=account_id, status="FAILED", error="broker gateway offline",
            )
            self._report_sink(rpt)
            return

        self._apply_runtime_account(account_id)

        signal = self._deserialize_signal(msg.get("signal", {}))
        policy = msg.get("order_type_policy", "LMT_then_MKT")
        risk = msg.get("risk")

        core = ExecutionCore(
            adapter=self._adapter,
            broker=self.broker,
            source_id=source_id,
            account_id=account_id,
            on_report=self._report_sink,
            should_continue=lambda: not self._is_paused() and not self._stop.is_set(),
        )
        final = self._run_in_thread(lambda: core.execute(signal, order_type_policy=policy, risk=risk))
        with self._idem_lock:
            self._idem[key] = final
        save_terminal(source_id, signal_id, account_id, final.to_dict())

    @staticmethod
    def _deserialize_signal(d: dict) -> Signal:
        from sigtrades_core.signal.models import Signal as S
        if hasattr(S, "from_dict"):
            try:
                return S.from_dict(d)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        # 退化：直接构造已知字段
        return S(
            signal_id=d.get("signal_id", ""),
            timestamp=d.get("timestamp", time.time()),
            action=d.get("action", ""),
            symbol=d.get("symbol", ""),
            quantity=d.get("quantity", 0),
            order_type=d.get("order_type", "MKT"),
            limit_price=d.get("limit_price"),
        )
