"""全站公告广播服务（简化版）。"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import InAppBroadcast, User, UserMembership, UserNotification

logger = logging.getLogger(__name__)

EMAIL_AUDIENCE_NONE = "none"
EMAIL_AUDIENCE_ALL = "all"
EMAIL_AUDIENCE_MEMBERS = "members"
VALID_EMAIL_AUDIENCES = (EMAIL_AUDIENCE_ALL, EMAIL_AUDIENCE_MEMBERS)


def _title_body_for_user(row: InAppBroadcast, lang: Optional[str]) -> tuple[str, str]:
    en = (lang or "").lower().startswith("en")
    if en:
        t = (row.title_en or "").strip() or (row.title_zh or "").strip()
        b = (row.body_md_en or "").strip() or (row.body_md_zh or "").strip()
    else:
        t = (row.title_zh or "").strip() or (row.title_en or "").strip()
        b = (row.body_md_zh or "").strip() or (row.body_md_en or "").strip()
    return t, b


def _validate_content(row: InAppBroadcast) -> Optional[str]:
    if not (row.title_zh or row.title_en or "").strip():
        return "请填写标题（至少一种语言）"
    if not (row.body_md_zh or row.body_md_en or "").strip():
        return "请填写正文 Markdown（至少一种语言）"
    return None


async def do_broadcast(db: AsyncSession, broadcast_id: UUID) -> dict[str, Any]:
    row = (
        await db.execute(select(InAppBroadcast).where(InAppBroadcast.id == broadcast_id))
    ).scalar_one_or_none()
    if not row:
        return {"error": "not_found", "detail": "记录不存在"}
    if row.revoked_at is not None:
        return {"error": "revoked", "detail": "已撤回，无法继续发送或补发；请新建一条。"}
    err = _validate_content(row)
    if err:
        return {"error": "empty_config", "detail": err}

    urows = (await db.execute(select(User.id, User.language))).all()
    ref_id = str(row.id)
    sent = 0
    batch: list[UserNotification] = []
    batch_size = 400

    for urow in urows:
        uid: UUID = urow[0]
        lang = urow[1]
        title, body = _title_body_for_user(row, lang)
        if not title or not body:
            continue
        batch.append(
            UserNotification(
                user_id=uid,
                type="product_announcement",
                title=title[:200],
                message=body,
                message_format="markdown",
                ref_id=ref_id,
            )
        )
        sent += 1
        if len(batch) >= batch_size:
            db.add_all(batch)
            await db.flush()
            batch.clear()

    if batch:
        db.add_all(batch)
        await db.flush()

    now = datetime.now(timezone.utc)
    row.send_count = int(row.send_count or 0) + 1
    if row.first_sent_at is None:
        row.first_sent_at = now
    row.last_sent_at = now
    row.updated_at = now

    logger.info("[broadcast] id=%s sent=%s send_count=%s", broadcast_id, sent, row.send_count)
    return {"sent": sent, "send_count": row.send_count}


async def count_email_recipients(db: AsyncSession, audience: str) -> int:
    if audience == EMAIL_AUDIENCE_ALL:
        return (await db.execute(select(func.count(User.id)))).scalar() or 0
    if audience == EMAIL_AUDIENCE_MEMBERS:
        subq = select(UserMembership.user_id).where(UserMembership.status == "active").distinct()
        return (await db.execute(select(func.count()).select_from(subq.subquery()))).scalar() or 0
    return 0
