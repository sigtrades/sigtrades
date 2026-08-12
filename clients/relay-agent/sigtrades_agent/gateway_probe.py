"""本地券商网关端口探测（启动 / 保存 / 首页状态共用）。"""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Iterable, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_PORTS: Dict[str, Tuple[str, int]] = {
    "ibkr": ("127.0.0.1", 7497),  # TWS paper；实盘 7496
    "futu": ("127.0.0.1", 11111),
}


def probe_port(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def port_is_listening(host: str, port: int) -> bool:
    """本机是否有进程在 LISTEN（不代表 API 已可握手）。"""
    try:
        import subprocess

        out = subprocess.check_output(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"], text=True)
        return bool(out.strip())
    except Exception:  # noqa: BLE001
        return False


def _offline_hint(broker: str) -> str:
    key = (broker or "").lower()
    if key == "ibkr":
        return "请启动 TWS"
    if key == "futu":
        return "请启动 OpenD"
    return "请启动本机券商客户端"


def diagnose_broker(broker: str, config: dict | None = None, *, timeout: float = 1.0) -> dict:
    """探测并给出可操作的错误说明（区分未启动 vs 端口卡住）。"""
    cfg = config or {}
    host = str(cfg.get("host", DEFAULT_PORTS.get(broker, ("127.0.0.1", 0))[0]))
    port = int(cfg.get("port", DEFAULT_PORTS.get(broker, ("127.0.0.1", 0))[1]) or 0)
    if not port:
        return {"ok": False, "host": host, "port": port, "error": "port not configured"}
    ok = probe_port(host, port, timeout=timeout)
    if ok:
        return {"ok": True, "host": host, "port": port, "error": None}
    listening = port_is_listening(host, port)
    if listening:
        if (broker or "").lower() == "ibkr":
            err = (
                f"{host}:{port} 端口在监听但 TCP/API 握手超时（不是 Agent 配置写错）。"
                "请完全退出并重启 TWS，登录后再点重连；"
                "确认 API 端口与所选模式一致（TWS 实盘 7496 / 模拟 7497）；"
                "若弹出 Accept incoming connection 请点允许。"
                "仍失败可暂时关掉 Clash/系统代理后再试。"
            )
        else:
            err = (
                f"{host}:{port} 端口在监听但 TCP/API 握手超时（不是 Agent 配置写错）。"
                "请完全退出并重启 OpenD 后再点重连；"
                "仍失败可暂时关掉 Clash/系统代理后再试。"
            )
    else:
        err = f"{host}:{port} 无进程监听 — {_offline_hint(broker)}"
    logger.info("网关诊断 %s %s:%s -> %s", broker, host, port, "OK" if ok else err[:40])
    return {"ok": False, "host": host, "port": port, "listening": listening, "error": err}


def probe_broker(broker: str, config: dict | None = None, *, timeout: float = 1.0) -> bool:
    cfg = config or {}
    host = cfg.get("host", DEFAULT_PORTS.get(broker, ("127.0.0.1", 0))[0])
    port = int(cfg.get("port", DEFAULT_PORTS.get(broker, ("127.0.0.1", 0))[1]))
    if not port:
        return False
    ok = probe_port(host, port, timeout=timeout)
    logger.info("网关探测 %s %s:%s -> %s", broker, host, port, "OK" if ok else "OFFLINE")
    return ok


def _profile_row(profile, *, online: bool) -> dict[str, Any]:
    cfg = dict(getattr(profile, "config", None) or {})
    return {
        "broker": profile.broker,
        "account_id": getattr(profile, "account_id", "") or "",
        "name": getattr(profile, "name", "") or getattr(profile, "account_id", "") or profile.broker,
        "online": online,
        "port": cfg.get("port"),
        "trd_env": cfg.get("trd_env"),
    }


def probe_profiles(
    profiles: Iterable,
    *,
    only_enabled: bool = True,
    timeout: float = 1.0,
) -> List[dict[str, Any]]:
    """并行探测各 profile，返回首页可用的 gateway 行。"""
    items = [p for p in profiles if (p.enabled if only_enabled else True)]
    if not items:
        return []

    results: dict[int, bool] = {}

    def _one(idx: int, profile) -> tuple[int, bool]:
        return idx, probe_broker(profile.broker, getattr(profile, "config", None) or {}, timeout=timeout)

    workers = min(8, len(items))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_one, i, p) for i, p in enumerate(items)]
        for fut in as_completed(futs):
            idx, ok = fut.result()
            results[idx] = ok
            if not ok:
                p = items[idx]
                logger.warning(
                    "[%s] 本机网关未就绪 profile=%s — %s",
                    p.broker,
                    getattr(p, "key", getattr(p, "account_id", "")),
                    _offline_hint(p.broker),
                )

    return [_profile_row(p, online=bool(results.get(i))) for i, p in enumerate(items)]


def probe_all_profiles(profiles) -> List[dict[str, Any]]:
    """兼容旧调用：探测已启用 profile 并返回结果行。"""
    return probe_profiles(profiles, only_enabled=True)
