"""云端券商执行（老虎 / 长桥 / 嘉信 / Alpaca / IBKR Web API）：共用 ExecutionCore，密钥运行时解密。"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

import httpx

from sigtrades_core.brokers import create_broker_adapter
from sigtrades_core.execution.core import ExecutionCore, ExecutionReportData
from sigtrades_core.signal.models import Signal

from app.config import settings
from app.crypto import decrypt

logger = logging.getLogger("cloud-executor")

_pool = ThreadPoolExecutor(max_workers=settings.MAX_WORKERS, thread_name_prefix="cloud-exec")
_HEADERS = {"X-Internal-Secret": settings.INTERNAL_SECRET}


async def resolve_credentials(user_id: str, broker: str, account_id: Optional[str],
                              account_label: Optional[str],
                              embedded: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """取得（密文）凭证并解密为可用 adapter config。

    dev：execute 信封可直接携带 broker_credentials（可为明文）。
    prod：向 api-server 取密文，本地 Fernet 解密 private_key。
    """
    creds = embedded
    if creds is None:
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            resp = await client.post(
                f"{settings.API_SERVER_URL}/internal/broker-credentials",
                json={
                    "user_id": user_id,
                    "broker": broker,
                    "account_id": account_id,
                    "account_label": account_label,
                },
                headers=_HEADERS,
            )
        if resp.status_code == 409:
            detail = resp.json().get("detail", {})
            labels = detail.get("labels") if isinstance(detail, dict) else None
            if labels:
                raise RuntimeError(
                    f"多个券商账号匹配，请在流水线执行步骤选择具体标识名后重新保存（可选: {', '.join(labels)}）"
                ) from None
        resp.raise_for_status()
        creds = resp.json()

    import json

    config = dict(creds.get("config", {}) or {})
    # 部分券商（如 ibkr_web）账户号在 credential 行上，内部接口未单独返回时靠调用方 account_id
    if account_id and not config.get("account_id"):
        config["account_id"] = account_id
    enc_pk = creds.get("private_key_encrypted")
    if enc_pk:
        config["private_key"] = decrypt(enc_pk)
    enc_secrets = creds.get("secrets_encrypted")
    if enc_secrets:
        secrets = json.loads(decrypt(enc_secrets))
        config.update(secrets)
    return config


def _run_execution(adapter_cfg: Dict[str, Any], broker: str, source_id: str,
                   account_id: Optional[str], signal: Signal, policy: str,
                   risk: Optional[Dict[str, Any]], report_sink,
                   user_id: str, should_continue) -> ExecutionReportData:
    try:
        adapter = create_broker_adapter(broker, adapter_cfg)
        if not adapter.connect():
            detail = getattr(adapter, "connect_error", None) or "券商连接失败"
            rpt = ExecutionReportData(
                signal_id=signal.signal_id, source_id=source_id, broker=broker,
                account_id=account_id, status="FAILED", error=detail,
            )
            report_sink(rpt)
            return rpt
        core = ExecutionCore(
            adapter=adapter, broker=broker, source_id=source_id,
            account_id=account_id, on_report=report_sink,
            should_continue=should_continue,
        )
        return core.execute(signal, order_type_policy=policy, risk=risk)
    except Exception as e:  # noqa: BLE001
        logger.exception("云端执行异常 signal_id=%s broker=%s", signal.signal_id, broker)
        rpt = ExecutionReportData(
            signal_id=signal.signal_id, source_id=source_id, broker=broker,
            account_id=account_id, status="FAILED", error=str(e),
        )
        report_sink(rpt)
        return rpt


def _fetch_kill_switch_sync(user_id: str) -> bool:
    """同步查询用户急停（在线程池内调用）。"""
    try:
        with httpx.Client(trust_env=False, timeout=3.0) as client:
            resp = client.get(
                f"{settings.API_SERVER_URL}/internal/user-kill-switch/{user_id}",
                headers=_HEADERS,
            )
        resp.raise_for_status()
        data = resp.json()
        return bool(data.get("kill_switch")) or not bool(data.get("is_active", True))
    except Exception as e:  # noqa: BLE001
        logger.warning("kill_switch 查询失败（继续执行）: %s", e)
        return False


async def execute(payload: Dict[str, Any], loop) -> Dict[str, Any]:
    """处理一条云端执行请求。回执通过 _report_sink 异步回传 api-server。"""
    user_id = payload["user_id"]
    broker = payload["broker"]
    account_id = payload.get("account_id")
    account_label = payload.get("account_label")
    source_id = payload.get("source_id", "")
    signal_id = payload.get("signal_id", "")
    policy = payload.get("order_type_policy", "LMT_then_MKT")
    risk = payload.get("risk")

    # A3：执行前检查急停（resolve-routing 之后用户仍可能开启 kill_switch）。
    if _fetch_kill_switch_sync(user_id):
        await _send_report(ExecutionReportData(
            signal_id=signal_id, source_id=source_id, broker=broker,
            account_id=account_id, status="SKIPPED", error="kill_switch",
        ), user_id)
        return {"accepted": False, "error": "kill_switch"}

    try:
        adapter_cfg = await resolve_credentials(
            user_id, broker, account_id, account_label, payload.get("broker_credentials")
        )
    except Exception as e:  # noqa: BLE001
        logger.error("解析凭证失败: %s", e)
        await _send_report(ExecutionReportData(
            signal_id=signal_id, source_id=source_id, broker=broker,
            account_id=account_id, status="FAILED", error=f"凭证解析失败: {e}",
        ), user_id)
        return {"accepted": False, "error": str(e)}

    signal = Signal.from_dict(payload.get("signal", {}))
    envelope_signal_id = payload.get("signal_id")
    if envelope_signal_id:
        signal.signal_id = str(envelope_signal_id)

    def report_sink(rpt: ExecutionReportData):
        asyncio.run_coroutine_threadsafe(_send_report(rpt, user_id), loop)

    should_continue = lambda: not _fetch_kill_switch_sync(user_id)

    exec_future = loop.run_in_executor(
        _pool,
        _run_execution,
        adapter_cfg,
        broker,
        source_id,
        account_id,
        signal,
        policy,
        risk,
        report_sink,
        user_id,
        should_continue,
    )
    try:
        final = await asyncio.wait_for(exec_future, timeout=float(settings.EXECUTE_TIMEOUT_SEC))
    except asyncio.TimeoutError:
        logger.error("云端执行超时 signal_id=%s broker=%s", signal_id, broker)
        await _send_report(
            ExecutionReportData(
                signal_id=signal_id,
                source_id=source_id,
                broker=broker,
                account_id=account_id,
                status="EXPIRED",
                error="执行超时：券商未在时限内返回终态",
            ),
            user_id,
        )
        return {"accepted": False, "error": "execute_timeout", "signal_id": signal_id}

    return {
        "accepted": True,
        "signal_id": signal_id,
        "status": final.status if final else None,
        "error": final.error if final else None,
    }


async def _send_report(rpt: ExecutionReportData, user_id: Optional[str] = None) -> None:
    try:
        payload = rpt.to_dict()
        if user_id:
            payload["user_id"] = user_id
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(settings.REPORT_SINK_URL, json=payload, headers=_HEADERS)
    except Exception as e:  # noqa: BLE001
        logger.warning("回传执行回执失败: %s", e)
