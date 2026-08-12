"""路由引擎：校验后的信号 → 动作裁决 → 分叉到老虎云执行 / relay Agent，并记录与通知。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Set

import httpx

from sigtrades_core.brokers import deployment_for

from app.config import settings
from app.models import (
    ActionType,
    BrokerBinding,
    InboundSignal,
    RouteOutcome,
    UserRoutePlan,
)

logger = logging.getLogger("signal-router")

_HEADERS = {"X-Internal-Secret": settings.INTERNAL_SECRET}
# 防止 create_task 被 GC 提前回收
_bg_tasks: Set[asyncio.Task] = set()


def _spawn_background(coro) -> None:
    task = asyncio.create_task(coro)
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)

IdemResult = Literal["ok", "duplicate", "check_failed"]


async def _check_idempotency(
    inbound: InboundSignal, account_id: str | None = None, user_id: str | None = None
) -> tuple[IdemResult, str | None]:
    """三态幂等检查：ok / duplicate / check_failed（api-server 不可用时）。"""
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
                resp = await client.post(
                    f"{settings.API_SERVER_URL}/internal/check-idempotency",
                    json={
                        "source_id": inbound.source_id,
                        "signal_id": inbound.signal_id,
                        "account_id": account_id,
                        "user_id": user_id,
                    },
                    headers=_HEADERS,
                )
            resp.raise_for_status()
            data = resp.json()
            if data.get("duplicate"):
                return "duplicate", data.get("status")
            return "ok", None
        except Exception as e:  # noqa: BLE001
            if attempt == 0:
                logger.warning("幂等检查失败，短重试: %s", e)
                continue
            logger.warning("幂等检查失败（跳过执行并通知）: %s", e)
            return "check_failed", str(e)
    return "check_failed", "unknown"


async def _acquire_inbound_once(inbound: InboundSignal) -> bool:
    """信号级幂等：同一 (source_id, signal_id) 只路由一次。

    上游（如 SunnyQuant 广播 worker）在未收到及时 2xx 时会按固定间隔重投同一信号；
    没有这道门闩时，拦截/待确认等不落幂等的路径会重复发通知、重建 PENDING 记录。
    api-server / redis 不可用时放行（fail-open），由账户级幂等兜底防重复下单。
    """
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            resp = await client.post(
                f"{settings.API_SERVER_URL}/internal/inbound-dedup",
                json={"source_id": inbound.source_id, "signal_id": inbound.signal_id},
                headers=_HEADERS,
            )
        resp.raise_for_status()
        return bool(resp.json().get("first", True))
    except Exception as e:  # noqa: BLE001
        logger.warning("信号级幂等检查失败，放行: %s", e)
        return True


async def _release_inbound_once(inbound: InboundSignal) -> None:
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(
                f"{settings.API_SERVER_URL}/internal/inbound-dedup",
                json={
                    "source_id": inbound.source_id,
                    "signal_id": inbound.signal_id,
                    "action": "release",
                },
                headers=_HEADERS,
            )
    except Exception:  # noqa: BLE001
        pass


def _placeholder_binding(plan: UserRoutePlan | None = None) -> BrokerBinding:
    """无券商绑定时的占位（用于拦截类记录）。

    优先写入规则目标券商，便于执行流水线按 broker 过滤时仍能展示。
    """
    broker = (plan.target_broker if plan and plan.target_broker else None) or "-"
    return BrokerBinding(broker=broker, account_id=None, device_id=None)


async def resolve_plans(inbound: InboundSignal) -> List[UserRoutePlan]:
    """解析该信号要影响哪些用户及其路由决策。

    优先用 api-server 解析（订阅关系 + entitlements + 风控 + route rules）；
    dev 模式允许 envelope 直接携带 plans。
    """
    if inbound.plans is not None and settings.DEV_ALLOW_EMBEDDED_PLAN:
        return inbound.plans
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            resp = await client.post(
                f"{settings.API_SERVER_URL}/internal/resolve-routing",
                json=inbound.model_dump(),
                headers=_HEADERS,
            )
        resp.raise_for_status()
        return [UserRoutePlan.model_validate(p) for p in resp.json().get("plans", [])]
    except Exception as e:  # noqa: BLE001
        logger.error("解析路由计划失败: %s", e)
        return inbound.plans or []


async def route_signal(inbound: InboundSignal) -> List[RouteOutcome]:
    if inbound.signal_id and not await _acquire_inbound_once(inbound):
        logger.info(
            "重复投递已忽略 source=%s signal=%s", inbound.source_id, inbound.signal_id,
        )
        return [RouteOutcome(user_id="-", broker="-", outcome="duplicate_inbound")]
    try:
        return await _route_signal_plans(inbound)
    except Exception:
        # 路由中途异常：释放门闩，让上游重投可恢复本条信号
        if inbound.signal_id:
            await _release_inbound_once(inbound)
        raise


async def _route_signal_plans(inbound: InboundSignal) -> List[RouteOutcome]:
    plans = await resolve_plans(inbound)
    outcomes: List[RouteOutcome] = []
    for plan in plans:
        if plan.risk_blocked:
            await _notify(inbound, plan, kind="risk_blocked", extra={"reason": plan.risk_blocked})
        # 权益/急停拦截：显式落库 SKIPPED + 通知，避免"信号凭空消失"。
        if plan.entitlement_blocked:
            await _record_execution(
                inbound, plan, _placeholder_binding(plan),
                status="SKIPPED", detail=f"entitlement:{plan.entitlement_blocked}",
            )
            await _notify(inbound, plan, kind="entitlement_blocked",
                          extra={"reason": plan.entitlement_blocked})
        if plan.action in (ActionType.NOTIFY_ONLY, ActionType.BOTH):
            await _notify(inbound, plan, kind="signal")
            if plan.action == ActionType.NOTIFY_ONLY:
                outcomes.append(RouteOutcome(user_id=plan.user_id, broker="-", outcome="notified"))
                continue
        if plan.action == ActionType.CONFIRM_TRADE:
            if not plan.bindings:
                if plan.risk_blocked:
                    outcomes.append(RouteOutcome(
                        user_id=plan.user_id, broker="-", outcome="risk_blocked", detail=plan.risk_blocked,
                    ))
                elif plan.routing_blocked:
                    await _record_execution(
                        inbound, plan, _placeholder_binding(plan),
                        status="FAILED", detail=f"routing:{plan.routing_blocked}",
                    )
                    outcomes.append(RouteOutcome(
                        user_id=plan.user_id, broker="-", outcome="skipped",
                        detail=f"routing:{plan.routing_blocked}",
                    ))
                elif plan.entitlement_blocked:
                    outcomes.append(RouteOutcome(
                        user_id=plan.user_id, broker="-", outcome="skipped",
                        detail=f"entitlement:{plan.entitlement_blocked}",
                    ))
                else:
                    await _record_execution(
                        inbound, plan, _placeholder_binding(plan),
                        status="SKIPPED", detail="routing:no_broker_binding",
                    )
                    outcomes.append(RouteOutcome(
                        user_id=plan.user_id, broker="-", outcome="skipped",
                        detail="routing:no_broker_binding",
                    ))
                continue
            expires = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat().replace("+00:00", "Z")
            for binding in plan.bindings:
                detail = json.dumps({
                    "expires_at": expires,
                    "order_type_policy": binding.order_type_policy,
                    "account_label": binding.account_label,
                })
                await _record_execution(
                    inbound, plan, binding, status="PENDING_CONFIRM", detail=detail,
                )
                await _notify(
                    inbound,
                    plan,
                    kind="pending_confirm",
                    extra={
                        "broker": binding.broker,
                        "account_id": binding.account_id,
                        "account_label": binding.account_label,
                    },
                )
                outcomes.append(RouteOutcome(
                    user_id=plan.user_id,
                    broker=binding.broker,
                    account_id=binding.account_id,
                    outcome="pending_confirm",
                ))
            continue
        if not plan.bindings:
            if plan.risk_blocked:
                outcomes.append(RouteOutcome(
                    user_id=plan.user_id, broker="-", outcome="risk_blocked", detail=plan.risk_blocked,
                ))
            elif plan.routing_blocked:
                await _record_execution(
                    inbound, plan, _placeholder_binding(plan),
                    status="FAILED", detail=f"routing:{plan.routing_blocked}",
                )
                outcomes.append(RouteOutcome(
                    user_id=plan.user_id, broker="-", outcome="skipped",
                    detail=f"routing:{plan.routing_blocked}",
                ))
            elif plan.entitlement_blocked:
                outcomes.append(RouteOutcome(
                    user_id=plan.user_id, broker="-", outcome="skipped",
                    detail=f"entitlement:{plan.entitlement_blocked}",
                ))
            else:
                # 有计划但无券商绑定：显式 SKIPPED，避免 token 已命中却 routed=0 静默消失
                await _record_execution(
                    inbound, plan, _placeholder_binding(plan),
                    status="SKIPPED", detail="routing:no_broker_binding",
                )
                outcomes.append(RouteOutcome(
                    user_id=plan.user_id, broker="-", outcome="skipped",
                    detail="routing:no_broker_binding",
                ))
            continue
        for binding in plan.bindings:
            outcomes.append(await _route_one(inbound, plan, binding))
    return outcomes


async def _route_one(inbound: InboundSignal, plan: UserRoutePlan, binding: BrokerBinding) -> RouteOutcome:
    idem, idem_detail = await _check_idempotency(inbound, binding.account_id, plan.user_id)
    if idem == "duplicate":
        logger.info("账户级幂等跳过 %s/%s/%s", inbound.source_id, inbound.signal_id, binding.account_id)
        return RouteOutcome(
            user_id=plan.user_id, broker=binding.broker, account_id=binding.account_id,
            outcome="duplicate", detail=idem_detail or "account idempotent skip",
        )
    if idem == "check_failed":
        await _record_execution(
            inbound, plan, binding, status="DEFERRED",
            detail=f"idempotency_unavailable:{idem_detail}",
        )
        await _notify(
            inbound, plan, kind="idempotency_unavailable",
            extra={"reason": idem_detail, "broker": binding.broker},
        )
        return RouteOutcome(
            user_id=plan.user_id, broker=binding.broker, account_id=binding.account_id,
            outcome="deferred", detail=idem_detail,
        )

    deployment = deployment_for(binding.broker)
    await _record_execution(inbound, plan, binding, status="ROUTING")

    if deployment == "cloud":
        return await _route_cloud(inbound, plan, binding)
    return await _route_relay(inbound, plan, binding)


def _signal_with_envelope_id(inbound: InboundSignal) -> dict:
    """确保 signal 内 signal_id 与信封一致，便于执行回报回写同一条流水线记录。"""
    signal = dict(inbound.signal or {})
    if inbound.signal_id:
        signal["signal_id"] = inbound.signal_id
    return signal


async def _route_cloud(inbound, plan, binding) -> RouteOutcome:
    """老虎等 REST 券商：异步交给 cloud-executor（不阻塞 webhook/ingest）。

    执行结果仍由 cloud-executor 经 execution-report 回写；此处只负责下发。
    """
    payload = {
        "user_id": plan.user_id,
        "signal_id": inbound.signal_id,
        "source_id": inbound.source_id,
        "broker": binding.broker,
        "account_id": binding.account_id,
        "account_label": binding.account_label,
        "order_type_policy": binding.order_type_policy,
        "signal": _signal_with_envelope_id(inbound),
        "execution_config": plan.execution_config,
        "risk": plan.risk,
    }

    async def _dispatch() -> None:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=130.0) as client:
                resp = await client.post(
                    f"{settings.CLOUD_EXECUTOR_URL}/internal/execute",
                    json=payload,
                    headers=_HEADERS,
                )
            resp.raise_for_status()
            logger.info(
                "云端执行已完成 signal_id=%s broker=%s",
                inbound.signal_id,
                binding.broker,
            )
        except Exception as e:  # noqa: BLE001
            logger.error("云端执行失败 signal_id=%s: %s", inbound.signal_id, e)
            await _record_execution(
                inbound, plan, binding, status="FAILED", detail=str(e),
            )

    _spawn_background(_dispatch())
    return RouteOutcome(
        user_id=plan.user_id,
        broker=binding.broker,
        account_id=binding.account_id,
        outcome="cloud_dispatched",
    )


async def _route_relay(inbound, plan, binding) -> RouteOutcome:
    """富途/IBKR：通过 relay-gateway 下发到本地 Agent。"""
    execute = {
        "type": "execute_signal",
        "signal_id": inbound.signal_id,
        "source_id": inbound.source_id,
        "broker": binding.broker,
        "account_id": binding.account_id,
        "order_type_policy": binding.order_type_policy,
        "signal": _signal_with_envelope_id(inbound),
        "execution_config": plan.execution_config,
        "risk": plan.risk,
    }
    payload = {"user_id": plan.user_id, "execute": execute, "device_id": binding.device_id}
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            resp = await client.post(
                f"{settings.RELAY_GATEWAY_URL}/internal/dispatch",
                json=payload, headers=_HEADERS,
            )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.error("relay 下发失败: %s", e)
        await _record_execution(inbound, plan, binding, status="FAILED", detail=str(e))
        return RouteOutcome(user_id=plan.user_id, broker=binding.broker,
                            account_id=binding.account_id, outcome="error", detail=str(e))

    if not data.get("delivered"):
        # Agent 离线：超时弃单 + 通知（默认不补单）
        await _record_execution(inbound, plan, binding, status="DISCARDED_AGENT_OFFLINE")
        await _notify(inbound, plan, kind="agent_offline", extra={"broker": binding.broker})
        return RouteOutcome(user_id=plan.user_id, broker=binding.broker,
                            account_id=binding.account_id, outcome="agent_offline",
                            detail=data.get("reason"))

    return RouteOutcome(user_id=plan.user_id, broker=binding.broker,
                        account_id=binding.account_id, outcome="dispatched",
                        detail=data.get("device_id"))


# ----------------------------------------------------------------------
# 落库 / 通知（向 api-server，失败不阻断路由）
# ----------------------------------------------------------------------
async def _record_execution(inbound, plan, binding, status: str, detail: str | None = None) -> None:
    payload = {
        "user_id": plan.user_id,
        "source_id": inbound.source_id,
        "signal_id": inbound.signal_id,
        "broker": binding.broker,
        "account_id": binding.account_id,
        "account_label": binding.account_label,
        "status": status,
        "detail": detail,
        "signal": inbound.signal,
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(
                f"{settings.API_SERVER_URL}/internal/execution-record",
                json=payload, headers=_HEADERS,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("写执行记录失败: %s", e)


async def _notify(inbound, plan, kind: str, extra: dict | None = None) -> None:
    payload = {
        "user_id": plan.user_id,
        "language": plan.language,
        "kind": kind,
        "source_id": inbound.source_id,
        "signal_id": inbound.signal_id,
        "signal": inbound.signal,
        "extra": extra or {},
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(settings.NOTIFY_URL, json=payload, headers=_HEADERS)
    except Exception as e:  # noqa: BLE001
        logger.warning("通知失败: %s", e)
