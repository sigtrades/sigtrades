"""用户 pipeline / brokers / agents / executions 聚合（后台只读）。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AgentPresenceRow,
    AgentToken,
    BrokerCredential,
    ExecutionRecord,
    UserBrokerBinding,
    UserParseRule,
    UserRouteRule,
    UserSourceSubscription,
    WebhookIngestToken,
)
from app.services.credential_mask import public_credential_row
from app.services.risk_disclosure import list_user_agreements
from app.utils.datetime import format_et


async def fetch_user_pipeline(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    subs = (
        await db.execute(
            select(UserSourceSubscription).where(UserSourceSubscription.user_id == user_id)
        )
    ).scalars().all()
    routes = (
        await db.execute(select(UserRouteRule).where(UserRouteRule.user_id == user_id))
    ).scalars().all()
    parse_rules = (
        await db.execute(select(UserParseRule).where(UserParseRule.user_id == user_id))
    ).scalars().all()
    webhooks = (
        await db.execute(select(WebhookIngestToken).where(WebhookIngestToken.user_id == user_id))
    ).scalars().all()

    return {
        "source_subscriptions": [
            {"source_id": s.source_id, "enabled": s.enabled} for s in subs
        ],
        "route_rules": [
            {
                "id": str(r.id),
                "source_id": r.source_id,
                "action": r.action,
                "order_type_policy": r.order_type_policy,
                "parse_mode": r.parse_mode,
                "signal_subtype": r.signal_subtype,
                "broker": r.broker,
                "account_id": r.account_id,
                "account_label": r.account_label,
                "default_quantity": r.default_quantity,
            }
            for r in routes
        ],
        "parse_rules": [
            {
                "id": str(p.id),
                "source_id": p.source_id,
                "parse_mode": p.parse_mode,
                "priority": p.priority,
                "label": p.label,
                "config": p.config,
            }
            for p in parse_rules
        ],
        "webhook_tokens": [
            {
                "id": str(w.id),
                "source_id": w.source_id,
                "label": w.label,
                "token_hint": (w.token[:4] + "••••") if w.token else "—",
            }
            for w in webhooks
        ],
    }


async def fetch_user_brokers(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    creds = (
        await db.execute(select(BrokerCredential).where(BrokerCredential.user_id == user_id))
    ).scalars().all()
    bindings = (
        await db.execute(select(UserBrokerBinding).where(UserBrokerBinding.user_id == user_id))
    ).scalars().all()

    return {
        "credentials": [public_credential_row(c) for c in creds],
        "bindings": [
            {
                "id": str(b.id),
                "broker": b.broker,
                "label": b.label,
                "account_id": b.account_id,
                "device_id": getattr(b, "device_id", None),
                "order_type_policy": getattr(b, "order_type_policy", None),
                "enabled": getattr(b, "enabled", True),
            }
            for b in bindings
        ],
    }


async def fetch_user_agents(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    tokens = (
        await db.execute(select(AgentToken).where(AgentToken.user_id == user_id))
    ).scalars().all()
    presence = (
        await db.execute(select(AgentPresenceRow).where(AgentPresenceRow.user_id == user_id))
    ).scalar_one_or_none()

    return {
        "tokens": [
            {
                "id": str(t.id),
                "label": t.label,
                "created_at": format_et(t.created_at),
                "revoked_at": format_et(t.revoked_at),
                "last_seen_at": format_et(t.last_seen_at),
                "token_hash_hint": (t.token_hash[:8] + "••••") if t.token_hash else "—",
            }
            for t in tokens
        ],
        "presence": None
        if not presence
        else {
            "online": presence.online,
            "brokers": presence.brokers,
            "updated_at": format_et(presence.updated_at),
        },
    }


async def fetch_user_executions(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    rows = (
        await db.execute(
            select(ExecutionRecord)
            .where(ExecutionRecord.user_id == user_id)
            .order_by(ExecutionRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
    ).scalars().all()

    return [
        {
            "id": str(e.id),
            "user_id": str(e.user_id),
            "source_id": e.source_id,
            "signal_id": e.signal_id,
            "broker": e.broker,
            "account_id": e.account_id,
            "account_label": e.account_label,
            "status": e.status,
            "detail": e.detail,
            "created_at": format_et(e.created_at),
        }
        for e in rows
    ]


async def fetch_user_risk_disclosures(db: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
    from app.services.risk_disclosure import RISK_DISCLOSURE_VERSION, user_has_agreed

    items = await list_user_agreements(db, user_id)
    return {
        "required_version": RISK_DISCLOSURE_VERSION,
        "accepted_current": await user_has_agreed(db, user_id, RISK_DISCLOSURE_VERSION),
        "items": items,
    }
