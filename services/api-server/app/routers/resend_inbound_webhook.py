"""Resend 入站 Webhook（根路径，与 Resend Dashboard 配置一致）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.inbound_mail_service import (
    fetch_received_email_from_resend,
    is_allowed_inbound_recipient,
    upsert_inbound_from_resend,
    verify_resend_webhook_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["resend-inbound"])


@router.post("/mail/webhook/received")
async def resend_mail_received(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    try:
        payload_str = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid body encoding") from exc

    svix_id = request.headers.get("svix-id")
    svix_ts = request.headers.get("svix-timestamp")
    svix_sig = request.headers.get("svix-signature")

    try:
        event = verify_resend_webhook_payload(payload_str, svix_id, svix_ts, svix_sig)
    except ValueError as e:
        logger.warning("inbound webhook verify failed: %s", e)
        raise HTTPException(status_code=401, detail=str(e)) from e

    event_type = event.get("type")
    if event_type != "email.received":
        return {"received": True, "ignored": True, "type": event_type}

    data = event.get("data") or {}
    email_id = data.get("email_id")
    if not email_id:
        raise HTTPException(status_code=400, detail="Missing data.email_id")

    # Webhook 已带收件人时先过滤，避免无谓拉取；否则拉正文后再判
    if is_allowed_inbound_recipient(data.get("to"), data.get("cc"), data.get("bcc")):
        allowed = True
    elif data.get("to") or data.get("cc") or data.get("bcc"):
        allowed = False
    else:
        allowed = None

    if allowed is False:
        logger.info(
            "inbound ignored (not @sigtrades.com): email_id=%s to=%s",
            email_id,
            data.get("to"),
        )
        return {"received": True, "ignored": True, "reason": "recipient_domain_not_allowed"}

    full, fetch_err = fetch_received_email_from_resend(email_id)
    if allowed is None and not is_allowed_inbound_recipient(
        (full or {}).get("to"),
        (full or {}).get("cc"),
        (full or {}).get("bcc"),
    ):
        logger.info(
            "inbound ignored after fetch (not @sigtrades.com): email_id=%s to=%s",
            email_id,
            (full or {}).get("to"),
        )
        return {"received": True, "ignored": True, "reason": "recipient_domain_not_allowed"}

    try:
        await upsert_inbound_from_resend(db, webhook_meta=data, full=full, fetch_error=fetch_err)
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.exception("inbound upsert failed email_id=%s", email_id)
        raise HTTPException(status_code=500, detail="Failed to store inbound email") from e

    if fetch_err:
        logger.warning("stored metadata but Receiving.get failed: %s", fetch_err)

    return {"received": True, "email_id": email_id}
