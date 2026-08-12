"""Resend 入站邮件：Webhook + Receiving API。"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import InboundEmail

logger = logging.getLogger(__name__)


def build_reply_subject(original: Optional[str]) -> str:
    base = (original or "").strip() or "(no subject)"
    if re.match(r"(?i)^re:\s*", base):
        return base
    return f"Re: {base}"


def format_thread_message_id(message_id: Optional[str]) -> Optional[str]:
    if not message_id:
        return None
    s = str(message_id).strip()
    if not s:
        return None
    if s.startswith("<") and s.endswith(">"):
        return s
    return f"<{s}>" if "@" in s else s


def parse_bare_email(from_header: str) -> str:
    if not from_header:
        return ""
    _, addr = parseaddr(from_header.strip())
    if addr:
        return addr.strip().lower()
    m = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", from_header)
    return (m.group(0) if m else from_header).strip().lower()


# 入站只落库收件域为 sigtrades.com 的邮件（含子域）；发往其它域的忽略。
ALLOWED_INBOUND_TO_DOMAIN = "sigtrades.com"


def _email_domain(addr: str) -> str:
    bare = parse_bare_email(addr)
    if not bare or "@" not in bare:
        return ""
    return bare.rsplit("@", 1)[-1]


def _domain_allowed(domain: str) -> bool:
    d = (domain or "").strip().lower().rstrip(".")
    if not d:
        return False
    return d == ALLOWED_INBOUND_TO_DOMAIN or d.endswith(f".{ALLOWED_INBOUND_TO_DOMAIN}")


def is_allowed_inbound_recipient(
    to_list: Any = None,
    cc_list: Any = None,
    bcc_list: Any = None,
) -> bool:
    """收件人/抄送/密送是否包含 *@sigtrades.com（含子域）。"""
    for raw in [*_as_list(to_list), *_as_list(cc_list), *_as_list(bcc_list)]:
        if _domain_allowed(_email_domain(str(raw or ""))):
            return True
    return False


def _parse_dt(val: Any) -> Optional[datetime]:
    if val is None:
        return None
    if isinstance(val, datetime):
        dt = val
    else:
        s = str(val).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _jsonb_safe(val: Any) -> Any:
    if val is None:
        return None
    try:
        return json.loads(json.dumps(val, default=str))
    except (TypeError, ValueError):
        return val


def _as_list(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def fetch_received_email_from_resend(email_id: str) -> tuple[Optional[dict], Optional[str]]:
    if not settings.RESEND_API_KEY:
        return None, "RESEND_API_KEY not configured"
    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        full = resend.Emails.Receiving.get(email_id)
        if isinstance(full, dict):
            return full, None
        return dict(full), None
    except Exception as e:  # noqa: BLE001
        logger.exception("Receiving.get failed email_id=%s", email_id)
        return None, str(e)


async def upsert_inbound_from_resend(
    db: AsyncSession,
    *,
    webhook_meta: dict[str, Any],
    full: Optional[dict[str, Any]],
    fetch_error: Optional[str],
) -> InboundEmail:
    email_id = webhook_meta.get("email_id") or ""
    if not email_id:
        raise ValueError("missing email_id")

    from_addr = str(webhook_meta.get("from") or "")
    to_list = _as_list(webhook_meta.get("to"))
    cc_list = _as_list(webhook_meta.get("cc"))
    bcc_list = _as_list(webhook_meta.get("bcc"))
    subject = webhook_meta.get("subject")
    message_id = webhook_meta.get("message_id")
    received_at = _parse_dt(webhook_meta.get("created_at"))

    html = None
    text = None
    headers = None
    attachments = _as_list(webhook_meta.get("attachments"))

    if full:
        html = full.get("html")
        text = full.get("text")
        headers = full.get("headers")
        if full.get("attachments"):
            attachments = _as_list(full.get("attachments"))
        if full.get("subject") is not None:
            subject = full.get("subject")
        if full.get("from"):
            from_addr = str(full.get("from"))
        if full.get("to"):
            to_list = _as_list(full.get("to"))
        if full.get("cc"):
            cc_list = _as_list(full.get("cc"))
        if full.get("bcc"):
            bcc_list = _as_list(full.get("bcc"))
        if full.get("message_id"):
            message_id = full.get("message_id")
        ra = _parse_dt(full.get("created_at"))
        if ra:
            received_at = ra

    result = await db.execute(
        select(InboundEmail).where(InboundEmail.resend_email_id == email_id)
    )
    row = result.scalar_one_or_none()
    if row:
        row.from_address = from_addr
        row.to_addresses = _jsonb_safe(to_list) or to_list
        row.cc = _jsonb_safe(cc_list) or (cc_list or [])
        row.bcc = _jsonb_safe(bcc_list) or (bcc_list or [])
        row.subject = subject
        row.message_id = message_id
        row.html = html
        row.text = text
        row.headers = _jsonb_safe(headers)
        row.attachments = _jsonb_safe(attachments) or attachments
        row.fetch_error = fetch_error
        row.received_at = received_at or row.received_at
        await db.flush()
        return row

    row = InboundEmail(
        resend_email_id=email_id,
        from_address=from_addr,
        to_addresses=_jsonb_safe(to_list) or to_list,
        cc=_jsonb_safe(cc_list) or (cc_list or []),
        bcc=_jsonb_safe(bcc_list) or (bcc_list or []),
        subject=subject,
        message_id=message_id,
        html=html,
        text=text,
        headers=_jsonb_safe(headers),
        attachments=_jsonb_safe(attachments) or attachments,
        fetch_error=fetch_error,
        received_at=received_at,
    )
    db.add(row)
    await db.flush()
    return row


def verify_resend_webhook_payload(
    payload_str: str,
    svix_id: Optional[str],
    svix_timestamp: Optional[str],
    svix_signature: Optional[str],
) -> dict[str, Any]:
    if not settings.RESEND_WEBHOOK_SECRET:
        if settings.ALLOW_INSECURE_INBOUND_WEBHOOK:
            logger.warning("inbound webhook: skipping Svix verify (ALLOW_INSECURE_INBOUND_WEBHOOK=true)")
            return json.loads(payload_str)
        raise ValueError("RESEND_WEBHOOK_SECRET not configured")
    if not all([svix_id, svix_timestamp, svix_signature]):
        raise ValueError("missing Svix headers")
    import resend

    resend.Webhooks.verify(
        {
            "payload": payload_str,
            "headers": {
                "id": svix_id,
                "timestamp": svix_timestamp,
                "signature": svix_signature,
            },
            "webhook_secret": settings.RESEND_WEBHOOK_SECRET,
        }
    )
    return json.loads(payload_str)


def fetch_inbound_attachment(email_id: str, attachment_id: str) -> tuple[Optional[bytes], Optional[str], str, Optional[str]]:
    """从 Resend Receiving API 拉取附件。返回 (content, content_type, filename, error)。"""
    if not settings.RESEND_API_KEY:
        return None, None, attachment_id, "RESEND_API_KEY not configured"
    try:
        import httpx

        url = f"https://api.resend.com/emails/receiving/{email_id}/attachments/{attachment_id}"
        resp = httpx.get(url, headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"}, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
        download_url = data.get("download_url") or data.get("url")
        filename = data.get("filename") or data.get("name") or attachment_id
        content_type = data.get("content_type") or "application/octet-stream"
        if download_url:
            dl = httpx.get(download_url, timeout=60.0)
            dl.raise_for_status()
            return dl.content, content_type, filename, None
        if data.get("content"):
            import base64
            return base64.b64decode(data["content"]), content_type, filename, None
        return None, None, filename, "no attachment content"
    except Exception as e:  # noqa: BLE001
        logger.exception("fetch attachment failed email_id=%s attachment_id=%s", email_id, attachment_id)
        return None, None, attachment_id, str(e)


async def fetch_inbound_attachment_async(email_id: str, attachment_id: str) -> tuple[Optional[bytes], Optional[str], str, Optional[str]]:
    import asyncio
    return await asyncio.to_thread(fetch_inbound_attachment, email_id, attachment_id)

