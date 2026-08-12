"""管理员 — 用户管理。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AgentToken, MembershipPlan, User, UserMembership
from app.routers.admin.deps import require_admin_only, verify_admin_context, verify_admin_token
from app.services.admin_user_detail import (
    fetch_user_agents,
    fetch_user_brokers,
    fetch_user_executions,
    fetch_user_pipeline,
    fetch_user_risk_disclosures,
)
from app.services.user_geo_service import (
    fetch_latest_login_by_users,
    fetch_registration_by_users,
    geo_snapshot,
)
from app.utils.datetime import format_et

router = APIRouter()


class BanBody(BaseModel):
    banned: bool = True
    note: Optional[str] = None


class KillSwitchBody(BaseModel):
    enabled: bool = True


def _user_row(u: User, reg_map, log_map, membership: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    row = {
        "id": str(u.id),
        "email": u.email,
        "display_name": u.display_name,
        "language": u.language,
        "auth_provider": u.auth_provider,
        "kill_switch": u.kill_switch,
        "is_banned": u.is_banned,
        "is_active": u.is_active,
        "admin_note": u.admin_note,
        "email_verified": u.email_verified,
        "created_at": format_et(u.created_at),
        "registration_geo": geo_snapshot(reg_map.get(u.id)),
        "last_login_geo": geo_snapshot(log_map.get(u.id)),
    }
    if membership is not None:
        row["membership"] = membership
    return row


async def _latest_memberships_for_users(
    db: AsyncSession, user_ids: list[uuid.UUID]
) -> dict[uuid.UUID, Dict[str, Any]]:
    if not user_ids:
        return {}
    rows = (
        await db.execute(
            select(UserMembership, MembershipPlan.code, MembershipPlan.name)
            .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
            .where(UserMembership.user_id.in_(user_ids))
            .order_by(UserMembership.user_id, UserMembership.created_at.desc())
        )
    ).all()
    out: dict[uuid.UUID, Dict[str, Any]] = {}
    for m, plan_code, plan_name in rows:
        if m.user_id in out:
            continue
        out[m.user_id] = {
            "id": str(m.id),
            "plan_code": plan_code,
            "plan_name": plan_name,
            "status": m.status,
            "period_end": format_et(m.period_end),
            "stripe_subscription_id": m.stripe_subscription_id,
        }
    return out


@router.get("")
async def list_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    q: Optional[str] = Query(None, description="邮箱搜索"),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.created_at.desc())
    count_stmt = select(func.count(User.id))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(User.email.ilike(like))
        count_stmt = count_stmt.where(User.email.ilike(like))

    total = (await db.execute(count_stmt)).scalar() or 0
    offset = (page - 1) * limit
    users = (await db.execute(stmt.offset(offset).limit(limit))).scalars().all()
    user_ids = [u.id for u in users]
    reg_map = await fetch_registration_by_users(db, user_ids)
    log_map = await fetch_latest_login_by_users(db, user_ids)
    membership_map = await _latest_memberships_for_users(db, user_ids)

    return {
        "success": True,
        "data": {
            "users": [
                _user_row(u, reg_map, log_map, membership_map.get(u.id)) for u in users
            ],
            "pagination": {
                "page": page,
                "limit": limit,
                "total": int(total),
                "pages": (int(total) + limit - 1) // limit if limit else 0,
            },
        },
    }


@router.get("/geo-distribution")
async def users_geo_distribution(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    from app.services.user_geo_service import (
        count_users_without_registration_event,
        country_distribution_by_registration_or_latest_login,
    )

    total = (await db.execute(select(func.count(User.id)))).scalar() or 0
    no_reg = await count_users_without_registration_event(db)
    distribution = await country_distribution_by_registration_or_latest_login(db)
    return {
        "success": True,
        "data": {
            "total_users": int(total),
            "users_without_registration_event": int(no_reg),
            "users_without_geo": int(distribution["users_without_geo"]),
            "users_fallback_to_last_login": int(distribution["users_fallback_to_last_login"]),
            "by_country": distribution["by_country"],
        },
    }


@router.get("/{user_id}")
async def get_user(
    user_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="not found")

    reg_map = await fetch_registration_by_users(db, [uid])
    log_map = await fetch_latest_login_by_users(db, [uid])
    membership_rows = (
        await db.execute(
            select(UserMembership, MembershipPlan.code, MembershipPlan.name)
            .join(MembershipPlan, MembershipPlan.id == UserMembership.plan_id)
            .where(UserMembership.user_id == uid)
            .order_by(UserMembership.created_at.desc())
        )
    ).all()

    data = _user_row(user, reg_map, log_map)
    data["memberships"] = [
        {
            "id": str(m.id),
            "plan_id": str(m.plan_id),
            "plan_code": plan_code,
            "plan_name": plan_name,
            "status": m.status,
            "stripe_subscription_id": m.stripe_subscription_id,
            "period_end": format_et(m.period_end),
            "created_at": format_et(m.created_at),
        }
        for m, plan_code, plan_name in membership_rows
    ]
    return {"success": True, "data": data}


@router.post("/{user_id}/ban")
async def ban_user(
    user_id: str,
    body: BanBody,
    ctx=Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="not found")

    user.is_banned = body.banned
    user.is_active = not body.banned
    if body.note is not None:
        user.admin_note = body.note.strip() or None
    await db.commit()
    return {"success": True, "data": {"is_banned": user.is_banned, "admin_note": user.admin_note}}


@router.post("/{user_id}/kill-switch")
async def set_kill_switch(
    user_id: str,
    body: KillSwitchBody,
    ctx=Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="not found")

    user.kill_switch = body.enabled
    await db.commit()
    return {"success": True, "data": {"kill_switch": user.kill_switch}}


@router.post("/{user_id}/revoke-tokens")
async def revoke_agent_tokens(
    user_id: str,
    ctx=Depends(require_admin_only),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")

    user = (await db.execute(select(User).where(User.id == uid))).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="not found")

    now = datetime.now(timezone.utc)
    tokens = (
        await db.execute(
            select(AgentToken).where(AgentToken.user_id == uid, AgentToken.revoked_at.is_(None))
        )
    ).scalars().all()
    for t in tokens:
        t.revoked_at = now
    user.token_version = (user.token_version or 0) + 1
    await db.commit()
    return {"success": True, "data": {"revoked_count": len(tokens), "token_version": user.token_version}}


@router.get("/{user_id}/pipeline")
async def user_pipeline(
    user_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")
    return {"success": True, "data": await fetch_user_pipeline(db, uid)}


@router.get("/{user_id}/brokers")
async def user_brokers(
    user_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")
    return {"success": True, "data": await fetch_user_brokers(db, uid)}


@router.get("/{user_id}/agents")
async def user_agents(
    user_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")
    return {"success": True, "data": await fetch_user_agents(db, uid)}


@router.get("/{user_id}/executions")
async def user_executions(
    user_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")
    offset = (page - 1) * limit
    items = await fetch_user_executions(db, uid, limit=limit, offset=offset)
    return {"success": True, "data": {"items": items, "page": page, "limit": limit}}


@router.get("/{user_id}/risk-disclosures")
async def user_risk_disclosures(
    user_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    try:
        uid = uuid.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid user id")
    return {"success": True, "data": await fetch_user_risk_disclosures(db, uid)}
