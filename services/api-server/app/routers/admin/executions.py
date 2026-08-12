"""管理员 — 执行记录。"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import BrokerCredential, ExecutionRecord, User
from app.routers.admin.deps import verify_admin_token
from app.services.trading_env import credential_env, env_label_zh, resolve_is_paper
from app.utils.datetime import format_et

router = APIRouter()


async def _credential_env_map(
    db: AsyncSession,
    rows: list[ExecutionRecord],
) -> dict[tuple[str, str, str], Optional[str]]:
    """(user_id, broker, account_key) -> env；account_key 为 account_id 或 label。"""
    user_ids = {e.user_id for e in rows if e.user_id}
    if not user_ids:
        return {}
    creds = (
        await db.execute(select(BrokerCredential).where(BrokerCredential.user_id.in_(user_ids)))
    ).scalars().all()
    out: dict[tuple[str, str, str], Optional[str]] = {}
    for c in creds:
        env = credential_env(c.config)
        uid = str(c.user_id)
        broker = (c.broker or "").lower()
        if c.account_id:
            out[(uid, broker, f"id:{c.account_id}")] = env
        if c.label:
            out[(uid, broker, f"label:{c.label}")] = env
    return out


def _lookup_env(
    env_map: dict[tuple[str, str, str], Optional[str]],
    e: ExecutionRecord,
) -> Optional[str]:
    uid = str(e.user_id)
    broker = (e.broker or "").lower()
    if e.account_id:
        hit = env_map.get((uid, broker, f"id:{e.account_id}"))
        if hit is not None:
            return hit
    if e.account_label:
        hit = env_map.get((uid, broker, f"label:{e.account_label}"))
        if hit is not None:
            return hit
    return None


def _execution_dict(
    e: ExecutionRecord,
    user_email: str | None = None,
    cred_env: str | None = None,
) -> dict:
    pnl = e.realized_pnl
    is_paper = resolve_is_paper(e.broker, e.account_id, cred_env)
    return {
        "id": str(e.id),
        "user_id": str(e.user_id),
        "user_email": user_email,
        "source_id": e.source_id,
        "signal_id": e.signal_id,
        "broker": e.broker,
        "account_id": e.account_id,
        "account_label": e.account_label,
        "is_paper": is_paper,
        "env_label": env_label_zh(is_paper),
        "status": e.status,
        "detail": e.detail,
        "channel_id": e.channel_id,
        "signal_subtype": e.signal_subtype,
        "realized_pnl": float(pnl) if pnl is not None else None,
        "created_at": format_et(e.created_at),
    }


@router.get("")
async def admin_executions(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    broker: Optional[str] = None,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExecutionRecord, User.email)
        .outerjoin(User, User.id == ExecutionRecord.user_id)
        .order_by(ExecutionRecord.created_at.desc())
    )
    count_stmt = select(func.count(ExecutionRecord.id))

    if user_id:
        try:
            uid = uuid.UUID(user_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid user_id")
        stmt = stmt.where(ExecutionRecord.user_id == uid)
        count_stmt = count_stmt.where(ExecutionRecord.user_id == uid)
    if status:
        stmt = stmt.where(ExecutionRecord.status == status)
        count_stmt = count_stmt.where(ExecutionRecord.status == status)
    if broker:
        stmt = stmt.where(ExecutionRecord.broker == broker)
        count_stmt = count_stmt.where(ExecutionRecord.broker == broker)

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * limit
    rows = (await db.execute(stmt.offset(offset).limit(limit))).all()
    execs = [e for e, _ in rows]
    env_map = await _credential_env_map(db, execs)

    return {
        "success": True,
        "data": {
            "items": [
                _execution_dict(e, email, _lookup_env(env_map, e)) for e, email in rows
            ],
            "pagination": {"page": page, "limit": limit, "total": int(total)},
        },
    }


@router.get("/{execution_id}")
async def get_execution(
    execution_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        eid = uuid.UUID(execution_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid id")

    row = (
        await db.execute(
            select(ExecutionRecord, User.email)
            .outerjoin(User, User.id == ExecutionRecord.user_id)
            .where(ExecutionRecord.id == eid)
        )
    ).one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    exec_row, email = row
    env_map = await _credential_env_map(db, [exec_row])
    data = _execution_dict(exec_row, email, _lookup_env(env_map, exec_row))
    data["signal"] = exec_row.signal
    return {"success": True, "data": data}
