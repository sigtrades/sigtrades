"""内部 API：供 relay-gateway / signal-router / cloud-executor 调用。"""

from __future__ import annotations

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import require_internal
from app.models import (
    AgentPresenceRow,
    BrokerCredential,
    ExecutionRecord,
    ExecutionReportRow,
    WebhookIngestToken,
)
from app.security import hash_agent_token
from app.services.execution_attrs import (
    coerce_realized_pnl,
    extract_channel_id,
    extract_signal_subtype,
)
from app.services.routing import resolve_routing_plans
from app.schemas import InboundSignalPayload

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal)])

# 视为"已处理"的终态：命中即不再因重复信号二次下单。
TERMINAL_STATUSES = (
    "FILLED",
    "PARTIALLY_FILLED",
    "REJECTED",
    "CANCELLED",
    "EXPIRED",
    "FAILED",
    "SKIPPED",
    "cloud_executed",
    "DISCARDED_AGENT_OFFLINE",
    "protective_failed",  # 主单已成交，保护单失败——不可再重复下单
)
# 在飞占位：回报到达前视为重复（见 IDEM_IN_FLIGHT_SEC 窗口）。
IN_FLIGHT_STATUSES = ("ROUTING", "DISPATCHED")
# 已提交订单的状态：同一 signal 不应再次下单。
ORDER_PLACED_STATUSES = (
    "ROUTING",
    "DISPATCHED",
    "SUBMITTED",
    "PENDING",
    "NEW",
    "UNKNOWN",
    "PARTIALLY_FILLED",
    "FILLED",
)


class VerifyAgentTokenRequest(BaseModel):
    user_token: str


class ClaimAgentWsRequest(BaseModel):
    user_token: str
    device_id: str


class AgentPresenceRequest(BaseModel):
    user_id: str
    online: bool
    brokers: Dict[str, bool] = {}


class ExecutionReportRequest(BaseModel):
    signal_id: str
    source_id: str
    broker: str
    status: str
    account_id: Optional[str] = None
    order_id: Optional[str] = None
    symbol: Optional[str] = None
    side: Optional[str] = None
    quantity: Optional[float] = None
    fill_price: Optional[float] = None
    amount: Optional[float] = None
    realized_pnl: Optional[float] = None
    attempt: Optional[int] = None
    error: Optional[str] = None
    user_id: Optional[str] = None


class ExecutionRecordRequest(BaseModel):
    user_id: str
    source_id: str
    signal_id: str
    broker: str
    account_id: Optional[str] = None
    account_label: Optional[str] = None
    status: str
    detail: Optional[str] = None
    signal: Dict[str, Any] = {}


class BrokerCredentialsRequest(BaseModel):
    user_id: str
    broker: str
    account_id: Optional[str] = None
    account_label: Optional[str] = None


class NotifyRequest(BaseModel):
    user_id: str
    language: str = "zh"
    kind: str
    source_id: str
    signal_id: str
    signal: Dict[str, Any] = {}
    extra: Dict[str, Any] = {}


@router.post("/verify-agent-token")
async def verify_agent_token(req: VerifyAgentTokenRequest, db: AsyncSession = Depends(get_db)):
    """兼容旧调用；relay-gateway 应优先使用 claim-agent-ws。"""
    from app.models import AgentToken, User

    token_hash = hash_agent_token(req.user_token)
    row = (
        await db.execute(
            select(AgentToken, User)
            .join(User, User.id == AgentToken.user_id)
            .where(AgentToken.token_hash == token_hash)
        )
    ).one_or_none()
    if row is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="invalid agent token")
    token, user = row
    if token.revoked_at is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="agent token revoked")
    if int(token.session_epoch or 0) != int(user.agent_session_epoch or 0):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="agent token superseded")
    return {"user_id": str(user.id)}


@router.post("/claim-agent-ws")
async def claim_agent_ws_endpoint(req: ClaimAgentWsRequest, db: AsyncSession = Depends(get_db)):
    from app.services.agent_session import claim_agent_ws

    user_id = await claim_agent_ws(db, req.user_token, req.device_id.strip())
    return {"user_id": user_id}


@router.post("/agent-presence")
async def agent_presence(req: AgentPresenceRequest, db: AsyncSession = Depends(get_db)):
    uid = uuid.UUID(req.user_id)
    stmt = insert(AgentPresenceRow).values(
        user_id=uid, online=req.online, brokers=req.brokers
    ).on_conflict_do_update(
        index_elements=["user_id"],
        set_={"online": req.online, "brokers": req.brokers},
    )
    await db.execute(stmt)
    await db.commit()
    return {"ok": True}


@router.post("/execution-report")
async def execution_report(req: ExecutionReportRequest, db: AsyncSession = Depends(get_db)):
    from app.services.notify_service import deliver
    from app.services.redis_client import idem_cache_set

    uid = None
    if req.user_id:
        try:
            uid = uuid.UUID(req.user_id)
        except ValueError:
            pass
    db.add(ExecutionReportRow(
        user_id=uid,
        signal_id=req.signal_id,
        source_id=req.source_id,
        broker=req.broker,
        account_id=req.account_id,
        status=req.status,
        payload=req.model_dump(),
    ))

    # 回报回写：用执行结果更新 signal-router 写入的 ROUTING 记录，
    # 让 Dashboard 看到真实状态，并关闭幂等（避免成交后重复信号再次下单）。
    rec_q = select(ExecutionRecord).where(
        ExecutionRecord.source_id == req.source_id,
        ExecutionRecord.signal_id == req.signal_id,
    )
    if uid:
        rec_q = rec_q.where(ExecutionRecord.user_id == uid)
    if req.account_id:
        rec_q = rec_q.where(ExecutionRecord.account_id == req.account_id)
    rec_q = rec_q.order_by(ExecutionRecord.created_at.desc()).limit(1)
    rec = (await db.execute(rec_q)).scalar_one_or_none()
    detail = _report_detail(req)
    pnl = coerce_realized_pnl(req.realized_pnl)
    if rec is not None:
        rec.status = req.status
        rec.detail = detail
        if pnl is not None:
            rec.realized_pnl = pnl
    elif uid is not None:
        # 无对应 ROUTING 记录（如回报早到/直连执行），补一条；user_id 为空则只存 report。
        db.add(ExecutionRecord(
            user_id=uid,
            source_id=req.source_id,
            signal_id=req.signal_id,
            broker=req.broker,
            account_id=req.account_id,
            status=req.status,
            detail=detail,
            signal={},
            realized_pnl=pnl,
        ))

    if req.status in TERMINAL_STATUSES:
        await idem_cache_set(
            req.source_id, req.signal_id, req.account_id, True,
            user_id=str(uid) if uid else None,
        )

    if uid and req.status in (
        "FILLED", "PARTIALLY_FILLED", "FAILED", "REJECTED", "CANCELLED", "protective_failed",
    ):
        from app.models import User

        user_result = await db.execute(select(User).where(User.id == uid))
        user = user_result.scalar_one_or_none()
        notify_kind = "protective_failed" if req.status == "protective_failed" else "execution"
        await deliver(
            db,
            user_id=uid,
            kind=notify_kind,
            language=user.language if user else "zh",
            payload=req.model_dump(),
        )
    await db.commit()
    return {"ok": True}


def _report_detail(req: "ExecutionReportRequest") -> str:
    parts = []
    if req.fill_price is not None:
        parts.append(f"fill={req.fill_price}")
    if req.order_id:
        parts.append(f"order={req.order_id}")
    if req.attempt is not None:
        parts.append(f"attempt={req.attempt}")
    if req.error:
        parts.append(f"err={req.error}")
    return "; ".join(parts) or req.status


@router.post("/resolve-routing")
async def resolve_routing(inbound: InboundSignalPayload, db: AsyncSession = Depends(get_db)):
    plans = await resolve_routing_plans(db, inbound.model_dump())
    return {"plans": plans}


@router.post("/execution-record")
async def execution_record(req: ExecutionRecordRequest, db: AsyncSession = Depends(get_db)):
    from app.services.redis_client import idem_cache_set

    uid = uuid.UUID(req.user_id)
    scope = select(ExecutionRecord).where(
        ExecutionRecord.user_id == uid,
        ExecutionRecord.source_id == req.source_id,
        ExecutionRecord.signal_id == req.signal_id,
        ExecutionRecord.broker == req.broker,
    )
    if req.account_id:
        scope = scope.where(ExecutionRecord.account_id == req.account_id)
    else:
        scope = scope.where(ExecutionRecord.account_id.is_(None))

    existing = (
        await db.execute(scope.order_by(ExecutionRecord.created_at.desc()).limit(1))
    ).scalar_one_or_none()

    incoming_active = req.status in ("ROUTING", "DISPATCHED", "PENDING_CONFIRM", "SUBMITTED", "PENDING", "NEW", "UNKNOWN")
    if existing and existing.status in TERMINAL_STATUSES and incoming_active:
        return {"ok": True, "skipped": True, "reason": "terminal_record_exists"}

    channel_id = extract_channel_id(req.signal)
    signal_subtype = extract_signal_subtype(req.signal)
    if existing:
        existing.status = req.status
        existing.detail = req.detail
        if req.account_label:
            existing.account_label = req.account_label
        if req.signal:
            existing.signal = req.signal
            if channel_id:
                existing.channel_id = channel_id
            if signal_subtype:
                existing.signal_subtype = signal_subtype
    else:
        db.add(ExecutionRecord(
            user_id=uid,
            source_id=req.source_id,
            signal_id=req.signal_id,
            broker=req.broker,
            account_id=req.account_id,
            account_label=req.account_label,
            status=req.status,
            detail=req.detail,
            signal=req.signal or {},
            channel_id=channel_id,
            signal_subtype=signal_subtype,
        ))
    await db.commit()
    if req.status in TERMINAL_STATUSES:
        await idem_cache_set(
            req.source_id, req.signal_id, req.account_id, True, user_id=req.user_id,
        )
    return {"ok": True}


@router.post("/broker-credentials")
async def broker_credentials(req: BrokerCredentialsRequest, db: AsyncSession = Depends(get_db)):
    q = select(BrokerCredential).where(
        BrokerCredential.user_id == uuid.UUID(req.user_id),
        BrokerCredential.broker == req.broker,
    )
    if req.account_label:
        q = q.where(BrokerCredential.label == req.account_label)
    elif req.account_id:
        q = q.where(BrokerCredential.account_id == req.account_id)
    result = await db.execute(q)
    creds = result.scalars().all()
    if not creds:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="credentials not found")
    if len(creds) > 1:
        from fastapi import HTTPException
        labels = [c.label for c in creds if c.label]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ambiguous_credentials",
                "message": "multiple credentials match; specify account_label",
                "labels": labels,
            },
        )
    cred = creds[0]
    cfg = dict(cred.config or {})
    if cred.account_id and not cfg.get("account_id"):
        cfg["account_id"] = cred.account_id
    return {
        "config": cfg,
        "private_key_encrypted": cred.private_key_encrypted,
        "secrets_encrypted": cred.secrets_encrypted,
    }


class ResolveWebhookTokenRequest(BaseModel):
    token: str


@router.post("/resolve-webhook-token")
async def resolve_webhook_token(req: ResolveWebhookTokenRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(WebhookIngestToken).where(WebhookIngestToken.token == req.token)
    )
    row = result.scalar_one_or_none()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="webhook token not found")
    return {
        "source_id": row.source_id,
        "owner_user_id": str(row.user_id),
        "hmac_secret": row.hmac_secret,
    }


@router.post("/notify")
async def notify(req: NotifyRequest, db: AsyncSession = Depends(get_db)):
    from app.services.notify_service import deliver

    await deliver(
        db,
        user_id=uuid.UUID(req.user_id),
        kind=req.kind,
        language=req.language,
        payload={
            "source_id": req.source_id,
            "signal_id": req.signal_id,
            "signal": req.signal,
            "extra": req.extra,
        },
    )
    await db.commit()
    return {"ok": True}


class ParseSignalRequest(BaseModel):
    user_id: str
    source_id: str
    sample: Any


@router.post("/parse-signal")
async def parse_signal(req: ParseSignalRequest, db: AsyncSession = Depends(get_db)):
    from app.config import settings
    from app.models import UserParseRule
    from app.services.entitlements import has_feature
    from sigtrades_core.parse import apply_parse_rules

    uid = uuid.UUID(req.user_id)
    result = await db.execute(
        select(UserParseRule).where(
            UserParseRule.user_id == uid,
            UserParseRule.source_id == req.source_id,
        )
    )
    rules = [
        {
            "parse_mode": r.parse_mode,
            "priority": r.priority,
            "config": r.config,
            "label": r.label,
        }
        for r in result.scalars().all()
    ]

    from app.models import SignalSource

    src_result = await db.execute(
        select(SignalSource).where(SignalSource.source_id == req.source_id)
    )
    src = src_result.scalar_one_or_none()
    option_default_dte = int((src.config or {}).get("option_default_dte", 0)) if src else 0

    allow_ai = await has_feature(db, uid, "ai_parse")
    parsed = await apply_parse_rules(
        req.sample,
        rules,
        allow_ai=allow_ai,
        option_default_dte=option_default_dte,
        **settings.ai_parse_kwargs(),
    )
    return {"signal": parsed.signal, "confidence": parsed.confidence, "mode": parsed.mode}


class InboundDedupRequest(BaseModel):
    source_id: str
    signal_id: str
    action: str = "acquire"  # acquire | release


@router.post("/inbound-dedup")
async def inbound_dedup(req: InboundDedupRequest):
    """信号级（source_id+signal_id）一次性门闩：上游重投同一信号时只路由第一次。

    redis 不可用时降级放行（first=True, degraded=True），
    此时仍有账户级 check-idempotency 兜底防止重复下单。
    """
    from app.services.redis_client import inbound_seen_acquire, inbound_seen_release

    if req.action == "release":
        await inbound_seen_release(req.source_id, req.signal_id)
        return {"ok": True}
    first = await inbound_seen_acquire(req.source_id, req.signal_id)
    return {"first": True if first is None else first, "degraded": first is None}


class IdempotencyCheckRequest(BaseModel):
    source_id: str
    signal_id: str
    account_id: Optional[str] = None
    user_id: Optional[str] = None


@router.post("/check-idempotency")
async def check_idempotency(req: IdempotencyCheckRequest, db: AsyncSession = Depends(get_db)):
    from datetime import timedelta

    from app.config import settings
    from app.services.redis_client import idem_cache_get, idem_cache_set

    cached = await idem_cache_get(req.source_id, req.signal_id, req.account_id, user_id=req.user_id)
    if cached is True:
        return {"duplicate": True, "status": "cached"}

    uid = None
    if req.user_id:
        try:
            uid = uuid.UUID(req.user_id)
        except ValueError:
            uid = None

    def _scope(q):
        if req.account_id:
            q = q.where(ExecutionRecord.account_id == req.account_id)
        if uid:
            q = q.where(ExecutionRecord.user_id == uid)
        return q

    q = _scope(select(ExecutionRecord).where(
        ExecutionRecord.source_id == req.source_id,
        ExecutionRecord.signal_id == req.signal_id,
        ExecutionRecord.status.in_(TERMINAL_STATUSES),
    ))
    row = (await db.execute(q.limit(1))).scalar_one_or_none()

    # 兜底：成交回报可能先于 record 回写到达，直接查 execution_reports。
    if row is None:
        rq = select(ExecutionReportRow).where(
            ExecutionReportRow.source_id == req.source_id,
            ExecutionReportRow.signal_id == req.signal_id,
            ExecutionReportRow.status.in_(TERMINAL_STATUSES),
        )
        if req.account_id:
            rq = rq.where(ExecutionReportRow.account_id == req.account_id)
        if uid:
            rq = rq.where(ExecutionReportRow.user_id == uid)
        rep = (await db.execute(rq.limit(1))).scalar_one_or_none()
        if rep is not None:
            is_dup = True
            status = rep.status
        else:
            is_dup = False
            status = None
    else:
        is_dup = True
        status = row.status

    if not is_dup:
        pq = _scope(select(ExecutionRecord).where(
            ExecutionRecord.source_id == req.source_id,
            ExecutionRecord.signal_id == req.signal_id,
            ExecutionRecord.status.in_(ORDER_PLACED_STATUSES),
        ))
        placed = (await db.execute(pq.limit(1))).scalar_one_or_none()
        if placed is not None:
            is_dup = True
            status = placed.status

    # A2 在飞去重：最近 N 秒内 ROUTING/DISPATCHED 视为占位锁，防止回报到达前二次下单。
    if not is_dup and settings.IDEM_IN_FLIGHT_SEC > 0:
        from datetime import datetime, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.IDEM_IN_FLIGHT_SEC)
        iq = _scope(select(ExecutionRecord).where(
            ExecutionRecord.source_id == req.source_id,
            ExecutionRecord.signal_id == req.signal_id,
            ExecutionRecord.status.in_(IN_FLIGHT_STATUSES),
            ExecutionRecord.created_at >= cutoff,
        ))
        in_flight = (await db.execute(iq.limit(1))).scalar_one_or_none()
        if in_flight is not None:
            is_dup = True
            status = in_flight.status

    await idem_cache_set(req.source_id, req.signal_id, req.account_id, is_dup, user_id=req.user_id)
    return {"duplicate": is_dup, "status": status}


@router.get("/user-kill-switch/{user_id}")
async def user_kill_switch(user_id: str, db: AsyncSession = Depends(get_db)):
    """供 cloud-executor / agent 执行前检查急停。"""
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="invalid user_id")
    from app.models import User

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="user not found")
    return {"kill_switch": bool(user.kill_switch), "is_active": bool(user.is_active)}


@router.get("/discord-sources")
async def discord_sources(db: AsyncSession = Depends(get_db)):
    import logging

    from app.models import SignalSource
    from app.services.crypto import decrypt

    log = logging.getLogger(__name__)
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.kind == "discord",
            SignalSource.is_active.is_(True),
        )
    )
    sources = []
    for s in result.scalars().all():
        cfg = s.config or {}
        if cfg.get("bridge_mode") == "personal":
            continue
        channel_ids = cfg.get("channel_ids") or []
        if not channel_ids:
            continue
        bot_token = None
        enc = cfg.get("bot_token_encrypted")
        if enc:
            try:
                bot_token = decrypt(enc)
            except Exception as e:  # noqa: BLE001
                log.warning("discord source %s bot_token decrypt failed: %s", s.source_id, e)
        sources.append({
            "source_id": s.source_id,
            "ownership": s.ownership,
            "owner_user_id": str(s.owner_user_id) if s.owner_user_id else cfg.get("owner_user_id"),
            "channel_ids": [str(c) for c in channel_ids],
            "bot_token": bot_token,
        })
    return {"sources": sources}


@router.get("/discord-user-sources")
async def discord_user_sources(db: AsyncSession = Depends(get_db)):
    import logging

    from app.models import SignalSource
    from app.services.crypto import decrypt

    log = logging.getLogger(__name__)
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.kind == "discord",
            SignalSource.is_active.is_(True),
        )
    )
    sources = []
    for s in result.scalars().all():
        cfg = s.config or {}
        if cfg.get("bridge_mode") != "personal":
            continue
        channel_ids = cfg.get("channel_ids") or []
        if not channel_ids:
            continue
        user_token = None
        enc = cfg.get("user_token_encrypted")
        if enc:
            try:
                user_token = decrypt(enc)
            except Exception as e:  # noqa: BLE001
                log.warning("discord user source %s decrypt failed: %s", s.source_id, e)
        if not user_token:
            continue
        sources.append({
            "source_id": s.source_id,
            "ownership": s.ownership,
            "owner_user_id": str(s.owner_user_id) if s.owner_user_id else cfg.get("owner_user_id"),
            "channel_ids": [str(c) for c in channel_ids],
            "channel_labels": cfg.get("channel_labels") or {},
            "user_token": user_token,
        })
    return {"sources": sources}


@router.get("/telegram-sources")
async def telegram_sources(db: AsyncSession = Depends(get_db)):
    from app.models import SignalSource

    result = await db.execute(
        select(SignalSource).where(
            SignalSource.kind == "telegram",
            SignalSource.is_active.is_(True),
        )
    )
    sources = []
    for s in result.scalars().all():
        cfg = s.config or {}
        chat_ids = cfg.get("chat_ids") or []
        if not chat_ids:
            continue
        sources.append({
            "source_id": s.source_id,
            "ownership": s.ownership,
            "owner_user_id": str(s.owner_user_id) if s.owner_user_id else cfg.get("owner_user_id"),
            "chat_ids": [str(c) for c in chat_ids],
        })
    return {"sources": sources}


class PartnerMintCodeRequest(BaseModel):
    campaign_key: str = "sunnyquant_pro_gift"
    external_ref: str
    partner: str = "sunnyquant"
    # SQ 会员绝对到期日（ISO8601）；兑换后 SigTrades period_end 严格等于此值
    period_end: str


@router.post("/partner/mint-code")
async def partner_mint_code(req: PartnerMintCodeRequest, db: AsyncSession = Depends(get_db)):
    """SunnyQuant 等合作方：按活动模板生成一次性兑换码（幂等 external_ref；到期对齐 period_end）。"""
    from app.services.promotion_redeem import mint_partner_code

    data = await mint_partner_code(
        db,
        campaign_key=req.campaign_key,
        external_ref=req.external_ref,
        partner=req.partner,
        period_end=req.period_end,
    )
    return {"success": True, "data": data}
