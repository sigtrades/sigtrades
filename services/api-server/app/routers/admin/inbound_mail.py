"""管理员 — 入站邮件。"""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timezone
from html import escape as html_escape
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import InboundEmail
from app.routers.admin.deps import verify_admin_token
from app.utils.datetime import format_et

router = APIRouter()


class InboundReplyBody(BaseModel):
    text: str = Field(..., min_length=1)
    html: Optional[str] = None


class OutboundEmailBody(BaseModel):
    from_email: Optional[str] = Field(None, max_length=320)
    to: str = Field(..., min_length=3, max_length=320)
    subject: str = Field(..., min_length=1, max_length=300)
    text: str = Field(..., min_length=1, max_length=10000)
    html: Optional[str] = Field(None, max_length=20000)


def _inbound_email_search_clause(email: str):
    q = (email or "").strip()
    if not q:
        return None
    pattern = f"%{q}%"
    return or_(
        InboundEmail.from_address.ilike(pattern),
        cast(InboundEmail.to_addresses, String).ilike(pattern),
        InboundEmail.text.ilike(pattern),
    )


def _first_to_bare(to_list: Any) -> str:
    from app.services.inbound_mail_service import parse_bare_email

    if not to_list:
        return ""
    first = to_list[0]
    if isinstance(first, str):
        return parse_bare_email(first)
    return parse_bare_email(str(first))


def _is_support_ticket(row: InboundEmail) -> bool:
    return (row.subject or "").strip().startswith("[客服工单]")


def _extract_support_ticket_contact_email(row: InboundEmail) -> str:
    from app.services.inbound_mail_service import parse_bare_email

    text = row.text or ""
    patterns = [
        r"联系邮箱[:：]\s*([^\s<>,;]+@[^\s<>,;]+)",
        r"Contact Email[:：]\s*([^\s<>,;]+@[^\s<>,;]+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return parse_bare_email(m.group(1))
    return ""


def _reply_target_for_row(row: InboundEmail) -> tuple[str, bool]:
    from app.services.inbound_mail_service import parse_bare_email

    if _is_support_ticket(row):
        contact_email = _extract_support_ticket_contact_email(row)
        return contact_email or parse_bare_email(row.from_address), True
    return parse_bare_email(row.from_address), False


def _display_subject_for_row(row: InboundEmail, reply_to_address: str, is_support_ticket: bool) -> Optional[str]:
    subject = row.subject
    if not subject or not is_support_ticket or not reply_to_address:
        return subject
    return re.sub(
        r"用户\s+[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\s*$",
        f"用户 {reply_to_address}",
        subject,
    )


def _row_to_list_item(row: InboundEmail) -> dict:
    reply_to_address, is_support_ticket = _reply_target_for_row(row)
    return {
        "id": str(row.id),
        "resend_email_id": row.resend_email_id,
        "from_address": row.from_address,
        "to_addresses": row.to_addresses or [],
        "subject": _display_subject_for_row(row, reply_to_address, is_support_ticket),
        "received_at": format_et(row.received_at),
        "created_at": format_et(row.created_at),
        "read_at": format_et(row.read_at),
        "is_read": row.read_at is not None,
        "fetch_error": row.fetch_error,
        "is_support_ticket": is_support_ticket,
        "reply_to_address": reply_to_address,
    }


def _row_to_detail(row: InboundEmail) -> dict:
    d = _row_to_list_item(row)
    d.update(
        {
            "cc": row.cc or [],
            "bcc": row.bcc or [],
            "message_id": row.message_id,
            "html": row.html,
            "text": row.text,
            "headers": row.headers,
            "attachments": row.attachments or [],
        }
    )
    return d


@router.get("")
async def list_inbound_mails(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    email: Optional[str] = Query(None, max_length=320),
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    email_clause = _inbound_email_search_clause(email or "")
    count_stmt = select(func.count()).select_from(InboundEmail)
    if email_clause is not None:
        count_stmt = count_stmt.where(email_clause)
    total = (await db.execute(count_stmt)).scalar() or 0
    stmt = select(InboundEmail)
    if email_clause is not None:
        stmt = stmt.where(email_clause)
    stmt = (
        stmt.order_by(InboundEmail.received_at.desc().nullslast(), InboundEmail.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(stmt)).scalars().all()
    total_pages = math.ceil(total / page_size) if page_size else 0
    return {
        "success": True,
        "data": {
            "items": [_row_to_list_item(r) for r in rows],
            "total": int(total),
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "pagination": {"page": page, "page_size": page_size, "total": int(total)},
        },
    }


@router.get("/unread-count")
async def inbound_unread_count(
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    n = (
        await db.execute(select(func.count()).select_from(InboundEmail).where(InboundEmail.read_at.is_(None)))
    ).scalar() or 0
    return {"success": True, "data": {"count": int(n)}}


@router.post("/send")
async def send_outbound_email(
    body: OutboundEmailBody,
    _: bool = Depends(verify_admin_token),
):
    from app.services.email_service import send_email
    from app.services.inbound_mail_service import parse_bare_email

    from_addr = parse_bare_email(body.from_email or settings.RESEND_FROM_EMAIL or "team@sigtrades.com")
    if not from_addr:
        raise HTTPException(status_code=400, detail="无法解析发件人邮箱")
    to_addr = parse_bare_email(body.to)
    if not to_addr:
        raise HTTPException(status_code=400, detail="无法解析收件人邮箱")

    html_body = body.html or (
        '<div style="font-family: system-ui, -apple-system, sans-serif; '
        "max-width: 640px; margin: 0 auto; padding: 20px; color: #1f2937; "
        'line-height: 1.7; white-space: pre-wrap;">'
        f"{html_escape(body.text)}"
        "</div>"
    )
    ok = send_email(
        to_addr,
        body.subject,
        html_body,
        body.text,
        from_email=from_addr,
    )
    if not ok:
        raise HTTPException(status_code=502, detail="通过 Resend 发送邮件失败，请检查日志与 RESEND_API_KEY")
    return {"success": True, "message": "邮件已发送", "data": {"to": to_addr, "from": from_addr}}


@router.get("/{mail_id}")
async def get_inbound_mail(
    mail_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InboundEmail).where(InboundEmail.id == uuid.UUID(mail_id)))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
    return {"success": True, "data": _row_to_detail(row)}


@router.post("/{mail_id}/read")
async def mark_inbound_read(
    mail_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    row = (await db.execute(select(InboundEmail).where(InboundEmail.id == uuid.UUID(mail_id)))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    row.read_at = datetime.now(timezone.utc)
    await db.commit()
    return {"success": True}


@router.post("/{mail_id}/reply")
async def reply_inbound_mail(
    mail_id: str,
    req: InboundReplyBody,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    from app.services.email_service import send_inbound_reply
    from app.services.inbound_mail_service import build_reply_subject, format_thread_message_id

    row = (await db.execute(select(InboundEmail).where(InboundEmail.id == uuid.UUID(mail_id)))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")

    from_mailbox = _first_to_bare(row.to_addresses) or (settings.RESEND_FROM_EMAIL or "").strip()
    if not from_mailbox:
        raise HTTPException(status_code=400, detail="无法解析入站收件地址（to_addresses 为空）")

    to_addr, is_support_ticket = _reply_target_for_row(row)
    if not to_addr:
        raise HTTPException(status_code=400, detail="无法解析回复目标邮箱")

    mid = None if is_support_ticket else format_thread_message_id(row.message_id)
    ok = send_inbound_reply(
        to_email=to_addr,
        from_email=from_mailbox,
        subject=build_reply_subject(row.subject),
        text_body=req.text,
        html_body=req.html,
        in_reply_to=mid,
    )
    if not ok:
        raise HTTPException(status_code=502, detail="send failed")
    return {"success": True, "message": "回复已发送"}


@router.get("/{mail_id}/attachments/{attachment_id}")
async def download_inbound_attachment(
    mail_id: str,
    attachment_id: str,
    _: bool = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db),
):
    from app.services.inbound_mail_service import fetch_inbound_attachment_async

    row = (await db.execute(select(InboundEmail).where(InboundEmail.id == uuid.UUID(mail_id)))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="not found")
    content, content_type, filename, err = await fetch_inbound_attachment_async(row.resend_email_id, attachment_id)
    if content is None:
        raise HTTPException(status_code=502, detail=err or "download failed")
    encoded = quote(filename)
    headers = {"Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded}'}
    return Response(content=content, media_type=content_type or "application/octet-stream", headers=headers)
