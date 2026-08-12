"""管理员 — Agent 在线状态。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import AgentPresenceRow, AgentToken, User
from app.routers.admin.deps import verify_admin_token
from app.utils.datetime import format_et

router = APIRouter()


def _presence_payload(rows, emails: dict[str, str] | None = None):
    emails = emails or {}
    return [
        {
            "user_id": str(r.user_id),
            "email": emails.get(str(r.user_id)),
            "online": r.online,
            "brokers": r.brokers,
            "updated_at": format_et(r.updated_at),
        }
        for r in rows
    ]


async def _user_emails(db: AsyncSession, user_ids: list) -> dict[str, str]:
    if not user_ids:
        return {}
    rows = (await db.execute(select(User.id, User.email).where(User.id.in_(user_ids)))).all()
    return {str(uid): email for uid, email in rows if email}


@router.get("")
async def admin_agents(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    presence_rows = (await db.execute(select(AgentPresenceRow))).scalars().all()
    token_counts = {}
    for row in (await db.execute(select(AgentToken.user_id))).all():
        uid = str(row[0])
        token_counts[uid] = token_counts.get(uid, 0) + 1

    emails = await _user_emails(db, [r.user_id for r in presence_rows])

    items = []
    for r in presence_rows:
        uid = str(r.user_id)
        items.append({
            "user_id": uid,
            "email": emails.get(uid),
            "online": r.online,
            "brokers": r.brokers,
            "updated_at": format_et(r.updated_at),
            "agent_token_count": token_counts.get(uid, 0),
        })

    return {"success": True, "data": items}


@router.get("/presence")
async def admin_agent_presence_alias(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(AgentPresenceRow))
    rows = result.scalars().all()
    emails = await _user_emails(db, [r.user_id for r in rows])
    return _presence_payload(rows, emails)
