"""resolve-routing：按源归属/订阅/权益/路由规则/风控生成 UserRoutePlan。

Webhook / user_private 源：执行账号仅由 ingest token → owner_user_id → 该用户的
route rule + broker binding 决定，不读取推送 JSON 里的 subscriber.email。
券商匹配以 account_id 为准（稳定身份）；account_label 仅在未配置 account_id 时兜底。
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    SignalSource,
    User,
    UserBrokerBinding,
    UserRouteRule,
    UserSourceSubscription,
)
from app.services.entitlements import can_auto_trade
from app.services.risk_service import check_risk


def _signal_subtype(inbound: Dict[str, Any]) -> Optional[str]:
    sig = inbound.get("signal") or {}
    st = sig.get("signal_subtype")
    if st:
        return str(st).upper()
    meta = sig.get("metadata") or {}
    action = (sig.get("action") or "").upper()
    if meta.get("subtype"):
        return str(meta["subtype"]).upper()
    if action in ("BUY", "SELL", "OPEN"):
        return "OPEN"
    if action in ("CLOSE", "EXIT"):
        return "CLOSE"
    return None


def _pick_route_rule(rules: List[UserRouteRule], subtype: Optional[str]) -> Optional[UserRouteRule]:
    if not rules:
        return None
    if subtype:
        for r in rules:
            if r.signal_subtype and r.signal_subtype.upper() == subtype:
                return r
    for r in rules:
        if not r.signal_subtype:
            return r
    return rules[0]


def _matching_route_rules(rules: List[UserRouteRule], subtype: Optional[str]) -> List[UserRouteRule]:
    """同一信号源可有多条路由（不同券商）；按 subtype 筛选后全部生效。"""
    if not rules:
        return []
    matched: List[UserRouteRule] = []
    for r in rules:
        if r.signal_subtype:
            if subtype and r.signal_subtype.upper() == subtype:
                matched.append(r)
        else:
            matched.append(r)
    if matched:
        return matched
    fallback = _pick_route_rule(rules, subtype)
    return [fallback] if fallback else []


def _apply_default_quantity(inbound: Dict[str, Any], rule: Optional[UserRouteRule]) -> Dict[str, Any]:
    if not rule or not rule.default_quantity:
        return inbound
    signal = dict(inbound.get("signal") or {})
    qty = signal.get("quantity")
    if qty is None or qty == 0:
        return {**inbound, "signal": {**signal, "quantity": rule.default_quantity}}
    return inbound


def select_bindings_for_rule(
    bindings: Sequence[UserBrokerBinding],
    rule: Optional[UserRouteRule],
) -> Tuple[List[UserBrokerBinding], Optional[str]]:
    """按路由规则挑选券商绑定。

    优先级：broker → account_id（稳定）→ account_label（仅无 account_id 时）。
    不依赖推送方邮箱；label 改名不影响已配置 account_id 的规则。
    """
    if not rule or not rule.broker:
        return list(bindings), None

    same_broker = [b for b in bindings if b.broker == rule.broker]
    if not same_broker:
        return [], "broker_binding_mismatch"

    wanted_id = (rule.account_id or "").strip()
    wanted_label = (rule.account_label or "").strip()

    if wanted_id:
        by_id = [b for b in same_broker if (b.account_id or "") == wanted_id]
        if by_id:
            return by_id, None
        return [], "broker_binding_mismatch"

    if wanted_label:
        by_label = [b for b in same_broker if (b.label or "") == wanted_label]
        if by_label:
            return by_label, None
        return [], "broker_binding_mismatch"

    distinct_labels = {(b.label or "").strip() for b in same_broker if (b.label or "").strip()}
    if len(same_broker) > 1 and len(distinct_labels) > 1:
        return [], "ambiguous_broker_account"
    return same_broker, None


async def _plan_for_rule(
    db: AsyncSession,
    user: User,
    uid: uuid.UUID,
    inbound: Dict[str, Any],
    rule: Optional[UserRouteRule],
    bindings: List[UserBrokerBinding],
) -> Dict[str, Any]:
    action = rule.action if rule else "auto_trade"
    broker_bindings: List[Dict[str, Any]] = []
    risk_payload: Dict[str, Any] = {}
    risk_reason: Optional[str] = None
    entitlement_reason: Optional[str] = None
    routing_blocked: Optional[str] = None
    risk_ok = True

    # 内容型信号（如 SunnyQuant sq_webhook_v2 结构提醒）不可下单：强制仅通知，
    # 避免 default_quantity 把 quantity=0 补成真实数量后误发券商。
    signal = inbound.get("signal") if isinstance(inbound.get("signal"), dict) else {}
    if signal.get("auto_trade_enabled") is False and action != "notify_only":
        action = "notify_only"

    if action in ("auto_trade", "both", "confirm_trade"):
        # 自动下单仅 Pro；免费/基础版可走确认后下单
        allowed = True
        if action in ("auto_trade", "both"):
            allowed, entitlement_reason = await can_auto_trade(db, user)
        risk_ok, risk_reason, risk_payload = await check_risk(db, uid, inbound.get("signal") or {})
        if not risk_ok and action in ("auto_trade", "confirm_trade"):
            action = "notify_only"
        elif not risk_ok and action == "both":
            action = "notify_only"
        if allowed and risk_ok:
            routed, routing_blocked = select_bindings_for_rule(bindings, rule)
            for b in routed:
                policy = b.order_type_policy
                if rule and rule.order_type_policy:
                    policy = rule.order_type_policy
                broker_bindings.append({
                    "broker": b.broker,
                    "account_id": b.account_id or None,
                    "account_label": b.label or None,
                    "device_id": b.device_id,
                    "order_type_policy": policy,
                })

    return {
        "user_id": str(uid),
        "action": action,
        "bindings": broker_bindings,
        "risk": risk_payload or None,
        "execution_config": None,
        "language": user.language or "zh",
        "risk_blocked": risk_reason,
        "entitlement_blocked": entitlement_reason,
        "routing_blocked": routing_blocked,
        # 拦截落库时写入目标券商，便于流水线按 broker 过滤仍能看见
        "target_broker": (rule.broker if rule and rule.broker else None),
    }


async def resolve_routing_plans(db: AsyncSession, inbound: Dict[str, Any]) -> List[Dict[str, Any]]:
    source_id = inbound.get("source_id", "")
    ownership = inbound.get("ownership", "user_private")
    owner_user_id = inbound.get("owner_user_id")
    subtype = _signal_subtype(inbound)

    src_result = await db.execute(
        select(SignalSource).where(SignalSource.source_id == source_id, SignalSource.is_active.is_(True))
    )
    source = src_result.scalar_one_or_none()
    if source:
        ownership = source.ownership
        owner_user_id = str(source.owner_user_id) if source.owner_user_id else owner_user_id

    user_ids: List[uuid.UUID] = []
    if ownership == "user_private" and owner_user_id:
        try:
            user_ids = [uuid.UUID(str(owner_user_id))]
        except ValueError:
            pass
    elif ownership == "platform_shared":
        sub_result = await db.execute(
            select(UserSourceSubscription).where(
                UserSourceSubscription.source_id == source_id,
                UserSourceSubscription.enabled.is_(True),
            )
        )
        user_ids = [s.user_id for s in sub_result.scalars().all()]

    plans: List[Dict[str, Any]] = []
    for uid in user_ids:
        user_result = await db.execute(select(User).where(User.id == uid, User.is_active.is_(True)))
        user = user_result.scalar_one_or_none()
        if not user:
            continue

        rules_result = await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.user_id == uid,
                UserRouteRule.source_id == source_id,
            )
        )
        rules = list(rules_result.scalars().all())
        applicable = [r for r in _matching_route_rules(rules, subtype) if r.is_active]

        bindings_result = await db.execute(
            select(UserBrokerBinding).where(
                UserBrokerBinding.user_id == uid,
                UserBrokerBinding.enabled.is_(True),
            )
        )
        bindings = bindings_result.scalars().all()

        if not applicable:
            plans.append(await _plan_for_rule(db, user, uid, inbound, None, bindings))
            continue

        for rule in applicable:
            rule_inbound = _apply_default_quantity(inbound, rule)
            plans.append(await _plan_for_rule(db, user, uid, rule_inbound, rule, bindings))

    return plans
