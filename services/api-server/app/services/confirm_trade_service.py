"""邮件一键确认/取消：签名 token + 与控制台相同的下单路径。

落地页只预览（GET）；真正执行走 POST，避免邮件安全扫描预取误下单。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional, Tuple

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ExecutionRecord
from app.security import create_state_token, decode_state_token, generate_verification_token
from app.services.redis_client import get_redis

logger = logging.getLogger(__name__)

Action = Literal["confirm", "reject"]
CONFIRM_TOKEN_TTL_MINUTES = 5
_REDIS_PREFIX = "confirm_action:jti:"


def issue_action_token(
    *,
    user_id: uuid.UUID | str,
    signal_id: str,
    source_id: str,
    action: Action,
    account_label: str = "",
    broker: str = "",
    account_id: str = "",
) -> str:
    """签发 5 分钟有效的确认/取消 token（type=confirm_action）。"""
    return create_state_token(
        {
            "type": "confirm_action",  # create_state_token 会覆盖 type 为 state；用 act 区分
            "act": action,
            "uid": str(user_id),
            "sid": str(signal_id),
            "src": str(source_id),
            "al": (account_label or "").strip(),
            "broker": (broker or "").strip(),
            "aid": (account_id or "").strip(),
            "jti": generate_verification_token()[:24],
            "purpose": "confirm_action",
        },
        ttl_minutes=CONFIRM_TOKEN_TTL_MINUTES,
    )


def _parse_token(token: str) -> Dict[str, Any]:
    payload = decode_state_token((token or "").strip())
    if not payload or payload.get("purpose") != "confirm_action":
        raise HTTPException(status_code=400, detail="invalid_token")
    act = str(payload.get("act") or "")
    if act not in {"confirm", "reject"}:
        raise HTTPException(status_code=400, detail="invalid_token")
    if not payload.get("uid") or not payload.get("sid") or not payload.get("src"):
        raise HTTPException(status_code=400, detail="invalid_token")
    return payload


async def _jti_consume(jti: str) -> bool:
    """一次性消费 jti；Redis 不可用时返回 True（依赖 PENDING_CONFIRM 状态防重放）。"""
    if not jti:
        return True
    r = await get_redis()
    if not r:
        return True
    try:
        ok = await r.set(
            f"{_REDIS_PREFIX}{jti}",
            "1",
            ex=CONFIRM_TOKEN_TTL_MINUTES * 60,
            nx=True,
        )
        return bool(ok)
    except Exception:  # noqa: BLE001
        return True


def _signal_summary(signal: dict | None) -> Dict[str, Any]:
    s = signal if isinstance(signal, dict) else {}
    return {
        "symbol": s.get("symbol") or s.get("ticker") or "",
        "side": s.get("side") or s.get("action") or "",
        "qty": s.get("qty") or s.get("quantity") or s.get("size") or "",
        "order_type": s.get("order_type") or s.get("type") or "",
        "raw": {k: s.get(k) for k in ("symbol", "side", "qty", "quantity", "price", "order_type") if k in s},
    }


async def find_pending_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    signal_id: str,
    source_id: str,
    account_label: str = "",
) -> Optional[ExecutionRecord]:
    result = await db.execute(
        select(ExecutionRecord)
        .where(
            ExecutionRecord.user_id == user_id,
            ExecutionRecord.signal_id == signal_id,
            ExecutionRecord.source_id == source_id,
            ExecutionRecord.status == "PENDING_CONFIRM",
        )
        .order_by(ExecutionRecord.created_at.desc())
    )
    pending = list(result.scalars().all())
    if not pending:
        return None
    wanted = (account_label or "").strip()
    if wanted:
        for row in pending:
            row_label = (row.account_label or "").strip()
            if not row_label and row.detail:
                try:
                    detail_obj = json.loads(row.detail)
                    if isinstance(detail_obj, dict):
                        row_label = str(detail_obj.get("account_label") or "").strip()
                except json.JSONDecodeError:
                    row_label = ""
            if row_label == wanted:
                return row
        return None
    return pending[0]


def _check_not_expired(record: ExecutionRecord) -> Tuple[dict, str]:
    detail: Dict[str, Any] = {}
    try:
        detail = json.loads(record.detail or "{}")
    except json.JSONDecodeError:
        detail = {}
    expires_at = detail.get("expires_at")
    if expires_at:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(status_code=400, detail="confirmation_expired")
    policy = str(detail.get("order_type_policy") or "MKT_only")
    return detail, policy


async def peek_action(db: AsyncSession, token: str) -> Dict[str, Any]:
    """预览：校验 token + 待确认记录，不改状态。"""
    payload = _parse_token(token)
    user_id = uuid.UUID(str(payload["uid"]))
    record = await find_pending_record(
        db,
        user_id=user_id,
        signal_id=str(payload["sid"]),
        source_id=str(payload["src"]),
        account_label=str(payload.get("al") or ""),
    )
    if record is None:
        raise HTTPException(status_code=404, detail="pending_not_found")
    try:
        _check_not_expired(record)
        expired = False
    except HTTPException as exc:
        if exc.detail == "confirmation_expired":
            expired = True
        else:
            raise

    return {
        "ok": True,
        "action": payload["act"],
        "expired": expired,
        "signal_id": record.signal_id,
        "source_id": record.source_id,
        "broker": record.broker,
        "account_id": record.account_id or payload.get("aid") or "",
        "account_label": record.account_label
        or str(payload.get("al") or "")
        or "",
        "signal": _signal_summary(record.signal),
        "expires_in_minutes": CONFIRM_TOKEN_TTL_MINUTES,
    }


async def _resolve_execution_account_label(
    db: AsyncSession,
    user_id: uuid.UUID,
    record: ExecutionRecord,
    account_label_hint: Optional[str] = None,
) -> str:
    # 延迟导入，避免与 config 路由循环依赖；逻辑与原 _resolve 对齐的最小集
    if account_label_hint and str(account_label_hint).strip():
        return str(account_label_hint).strip()
    if record.account_label and str(record.account_label).strip():
        return str(record.account_label).strip()
    try:
        detail = json.loads(record.detail or "{}")
        if isinstance(detail, dict) and detail.get("account_label"):
            return str(detail["account_label"]).strip()
    except json.JSONDecodeError:
        pass
    return ""


async def _dispatch_confirmed_trade(
    db: AsyncSession,
    user_id: uuid.UUID,
    record: ExecutionRecord,
    policy: str,
    account_label_hint: Optional[str] = None,
) -> None:
    from sigtrades_core.brokers import deployment_for

    headers = {"X-Internal-Secret": settings.INTERNAL_SECRET}
    deployment = deployment_for(record.broker)
    account_label = await _resolve_execution_account_label(
        db, user_id, record, account_label_hint
    )
    signal_payload = dict(record.signal or {})
    signal_payload["signal_id"] = record.signal_id

    if deployment == "cloud":
        payload = {
            "user_id": str(user_id),
            "signal_id": record.signal_id,
            "source_id": record.source_id,
            "broker": record.broker,
            "account_id": record.account_id,
            "account_label": account_label,
            "order_type_policy": policy,
            "signal": signal_payload,
        }
        async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CLOUD_EXECUTOR_URL}/internal/execute",
                json=payload,
                headers=headers,
            )
        resp.raise_for_status()
        return

    execute = {
        "type": "execute_signal",
        "signal_id": record.signal_id,
        "source_id": record.source_id,
        "broker": record.broker,
        "account_id": record.account_id,
        "account_label": account_label,
        "order_type_policy": policy,
        "signal": signal_payload,
    }
    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.post(
            f"{settings.RELAY_GATEWAY_URL}/internal/dispatch",
            json={"user_id": str(user_id), "execute": execute},
            headers=headers,
        )
    resp.raise_for_status()


async def execute_action(db: AsyncSession, token: str) -> Dict[str, Any]:
    """执行确认或取消（POST）。"""
    payload = _parse_token(token)
    jti = str(payload.get("jti") or "")
    if not await _jti_consume(jti):
        raise HTTPException(status_code=400, detail="token_used")

    user_id = uuid.UUID(str(payload["uid"]))
    account_label = str(payload.get("al") or "").strip()
    record = await find_pending_record(
        db,
        user_id=user_id,
        signal_id=str(payload["sid"]),
        source_id=str(payload["src"]),
        account_label=account_label,
    )
    if record is None:
        raise HTTPException(status_code=404, detail="pending_not_found")

    action = payload["act"]
    if action == "reject":
        record.status = "REJECTED"
        record.detail = "user rejected via email"
        await db.commit()
        return {"ok": True, "status": record.status, "action": "reject"}

    try:
        detail, policy = _check_not_expired(record)
    except HTTPException as exc:
        if exc.detail == "confirmation_expired":
            record.status = "EXPIRED"
            record.detail = "confirmation expired"
            await db.commit()
        raise

    if account_label and not record.account_label:
        record.account_label = account_label
    elif detail.get("account_label") and not record.account_label:
        record.account_label = str(detail["account_label"]).strip()
    record.status = "ROUTING"
    record.detail = "dispatching"
    await db.commit()

    try:
        await _dispatch_confirmed_trade(db, user_id, record, policy, account_label or None)
    except HTTPException:
        record.status = "FAILED"
        await db.commit()
        raise
    except Exception as e:  # noqa: BLE001
        record.status = "FAILED"
        record.detail = str(e)
        await db.commit()
        logger.exception("email confirm dispatch failed: %s", e)
        raise HTTPException(status_code=502, detail="dispatch_failed") from e

    return {"ok": True, "status": record.status, "action": "confirm"}


def action_urls(*, confirm_token: str, reject_token: str) -> Tuple[str, str]:
    base = settings.FRONTEND_URL.rstrip("/")
    return (
        f"{base}/confirm-trade?token={confirm_token}",
        f"{base}/confirm-trade?token={reject_token}",
    )
