"""嘉信 OAuth：对齐官方 Authenticate with OAuth（Authorization Code）。

授权链接仅含 client_id + redirect_uri；用户粘贴回跳 URL（含 code）完成换票。
"""

from __future__ import annotations

import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.config import settings
from app.database import get_db
from app.deps import get_verified_user
from app.models import BrokerCredential, User
from app.services.credential_mask import mask_secret, public_credential_row
from app.services.crypto import decrypt, encrypt
from app.services import schwab_oauth as schwab_oauth_svc

logger = logging.getLogger(__name__)
router = APIRouter(tags=["schwab-oauth"])


class SchwabOAuthStartRequest(BaseModel):
    cred_id: str | None = None
    label: str | None = Field(default=None, max_length=128)
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None


class SchwabOAuthCompleteRequest(BaseModel):
    cred_id: str
    redirected_url: str = Field(min_length=8)


async def _apply_token_payload(
    *,
    db: AsyncSession,
    cred: BrokerCredential,
    secrets: dict,
    token_payload: dict,
    redirect: str,
) -> BrokerCredential:
    access_token = str(token_payload.get("access_token") or "").strip()
    refresh_token = str(token_payload.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise RuntimeError("token_incomplete")
    accounts = await schwab_oauth_svc.fetch_account_numbers(access_token)
    hash_value, account_number = schwab_oauth_svc.pick_primary_account(accounts)
    if not hash_value:
        raise RuntimeError("no_account")

    secrets["refresh_token"] = refresh_token
    secrets["account_hash"] = hash_value
    secrets["access_token"] = access_token

    config = dict(cred.config or {})
    config["refresh_token_hint"] = mask_secret(refresh_token)
    config["account_hash_hint"] = mask_secret(hash_value)
    config["oauth_status"] = "authorized"
    config["oauth_redirect_uri"] = redirect
    config.pop("oauth_pending", None)
    if account_number:
        cred.account_id = account_number
        config["account_number"] = account_number

    cred.secrets_encrypted = encrypt(json.dumps(secrets, ensure_ascii=False))
    cred.config = config
    flag_modified(cred, "config")
    await db.commit()
    await db.refresh(cred)
    return cred


@router.get("/schwab/oauth/redirect-uri")
async def schwab_oauth_redirect_uri(user: User = Depends(get_verified_user)):
    _ = user
    return {"redirect_uri": schwab_oauth_svc.redirect_uri()}


@router.post("/schwab/oauth/start")
async def schwab_oauth_start(
    req: SchwabOAuthStartRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    cred: BrokerCredential | None = None
    if req.cred_id:
        try:
            cred_uuid = uuid.UUID(req.cred_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid cred_id") from exc
        result = await db.execute(
            select(BrokerCredential).where(
                BrokerCredential.id == cred_uuid,
                BrokerCredential.user_id == user.id,
                BrokerCredential.broker == "schwab",
            )
        )
        cred = result.scalar_one_or_none()
        if cred is None:
            raise HTTPException(status_code=404, detail="credential not found")

    secrets: dict = {}
    if cred and cred.secrets_encrypted:
        try:
            secrets = json.loads(decrypt(cred.secrets_encrypted))
        except Exception:  # noqa: BLE001
            secrets = {}

    stored_redirect = str((cred.config or {}).get("oauth_redirect_uri") or "").strip() if cred else ""
    redirect = schwab_oauth_svc.redirect_uri(req.redirect_uri or stored_redirect or None)
    if not redirect:
        raise HTTPException(status_code=500, detail="SCHWAB_OAUTH_REDIRECT_URI not configured")

    client_id = (req.client_id or "").strip() or str(secrets.get("client_id") or "").strip()
    client_secret = (req.client_secret or "").strip() or str(secrets.get("client_secret") or "").strip()
    label = (req.label or "").strip() or (cred.label if cred else "") or str((cred.config or {}).get("label") or "")
    label = str(label).strip()

    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="client_id and client_secret required")
    if not cred and not label:
        raise HTTPException(status_code=400, detail="label required")

    if cred is None:
        result = await db.execute(
            select(BrokerCredential).where(
                BrokerCredential.user_id == user.id,
                BrokerCredential.label == label,
            )
        )
        existing = result.scalar_one_or_none()
        if existing and existing.broker != "schwab":
            raise HTTPException(status_code=400, detail="label already used by another broker")
        cred = existing

    secrets["client_id"] = client_id
    secrets["client_secret"] = client_secret

    config = dict(cred.config or {}) if cred else {}
    config["label"] = label
    config["env"] = "live"
    config["client_id_hint"] = mask_secret(client_id)
    config["client_secret_hint"] = mask_secret(client_secret)
    config["oauth_redirect_uri"] = redirect
    config["oauth_pending"] = True
    if not secrets.get("refresh_token") or not secrets.get("account_hash"):
        config["oauth_status"] = "pending"

    if cred is None:
        cred = BrokerCredential(
            user_id=user.id,
            broker="schwab",
            account_id=f"schwab-{uuid.uuid4().hex[:10]}",
            label=label,
            config=config,
            secrets_encrypted=encrypt(json.dumps(secrets, ensure_ascii=False)),
        )
        db.add(cred)
    else:
        cred.broker = "schwab"
        if label:
            cred.label = label
        cred.config = config
        cred.secrets_encrypted = encrypt(json.dumps(secrets, ensure_ascii=False))
        flag_modified(cred, "config")

    await db.commit()
    await db.refresh(cred)

    # 官方格式：仅 client_id + redirect_uri
    authorize_url = schwab_oauth_svc.build_authorize_url(client_id, redirect=redirect)
    return {
        "ok": True,
        "authorize_url": authorize_url,
        "redirect_uri": redirect,
        "credential": public_credential_row(cred),
    }


@router.post("/schwab/oauth/complete")
async def schwab_oauth_complete(
    req: SchwabOAuthCompleteRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """粘贴嘉信回跳后的完整地址栏 URL（含 code=），完成本地授权。"""
    try:
        cred_uuid = uuid.UUID(req.cred_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid cred_id") from exc

    result = await db.execute(
        select(BrokerCredential).where(
            BrokerCredential.id == cred_uuid,
            BrokerCredential.user_id == user.id,
            BrokerCredential.broker == "schwab",
        )
    )
    cred = result.scalar_one_or_none()
    if cred is None or not cred.secrets_encrypted:
        raise HTTPException(status_code=404, detail="credential not found")

    try:
        code = schwab_oauth_svc.parse_redirected_url(req.redirected_url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid redirected url: {exc}") from exc

    redirect = schwab_oauth_svc.redirect_uri(
        str((cred.config or {}).get("oauth_redirect_uri") or "") or None
    )

    try:
        secrets = json.loads(decrypt(cred.secrets_encrypted))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="decrypt_failed") from exc

    client_id = str(secrets.get("client_id") or "").strip()
    client_secret = str(secrets.get("client_secret") or "").strip()
    if not client_id or not client_secret:
        raise HTTPException(status_code=400, detail="missing_client")

    try:
        token_payload = await schwab_oauth_svc.exchange_authorization_code(
            client_id=client_id,
            client_secret=client_secret,
            code=code,
            redirect=redirect,
        )
        cred = await _apply_token_payload(
            db=db,
            cred=cred,
            secrets=secrets,
            token_payload=token_payload,
            redirect=redirect,
        )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).strip() or repr(exc)
        logger.exception("schwab oauth complete failed: %s", msg)
        raise HTTPException(status_code=400, detail=f"exchange_failed: {msg}") from exc

    return {"ok": True, "credential": public_credential_row(cred)}


@router.get("/schwab/oauth/callback")
async def schwab_oauth_callback(request: Request):
    """若 Portal Callback 指向 API，把 query 原样转到前端 /schwab/callback 自动完成。"""
    frontend = settings.FRONTEND_URL.rstrip("/")
    qs = request.url.query
    target = f"{frontend}/schwab/callback"
    if qs:
        target = f"{target}?{qs}"
    return RedirectResponse(url=target, status_code=302)
