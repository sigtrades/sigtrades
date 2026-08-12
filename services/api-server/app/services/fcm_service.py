"""FCM HTTP v1 API（Service Account + OAuth2）。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_INVALID_TOKEN_ERRORS = frozenset({
    "UNREGISTERED",
    "INVALID_ARGUMENT",
    "NOT_FOUND",
})

_token_lock = asyncio.Lock()
_cached_token: Optional[str] = None
_token_expiry: Optional[datetime] = None


def _credentials():
    """加载 Firebase Service Account 凭证。"""
    if not settings.FCM_PROJECT_ID:
        return None
    try:
        from google.oauth2 import service_account

        if settings.FCM_CREDENTIALS_JSON:
            info = json.loads(settings.FCM_CREDENTIALS_JSON)
            return service_account.Credentials.from_service_account_info(info, scopes=[_FCM_SCOPE])
        if settings.FCM_CREDENTIALS_PATH:
            return service_account.Credentials.from_service_account_file(
                settings.FCM_CREDENTIALS_PATH, scopes=[_FCM_SCOPE]
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("FCM credentials load failed: %s", e)
    return None


def _refresh_access_token_sync() -> tuple[Optional[str], Optional[datetime]]:
    """同步刷新 token（供 asyncio.to_thread 调用）。"""
    creds = _credentials()
    if not creds:
        return None, None
    from google.auth.transport.requests import Request

    creds.refresh(Request())
    return creds.token, creds.expiry


async def _access_token() -> Optional[str]:
    global _cached_token, _token_expiry
    async with _token_lock:
        now = datetime.now(timezone.utc)
        if _cached_token and _token_expiry and now < _token_expiry - timedelta(seconds=60):
            return _cached_token
        try:
            result = await asyncio.to_thread(_refresh_access_token_sync)
            if not result:
                return None
            token, expiry = result
            _cached_token = token
            if expiry:
                _token_expiry = expiry.replace(tzinfo=timezone.utc) if expiry.tzinfo is None else expiry
            else:
                _token_expiry = now + timedelta(minutes=50)
            return _cached_token
        except Exception as e:  # noqa: BLE001
            logger.warning("FCM access token refresh failed: %s", e)
            return None


def fcm_enabled() -> bool:
    return bool(settings.FCM_PROJECT_ID and (settings.FCM_CREDENTIALS_JSON or settings.FCM_CREDENTIALS_PATH))


async def send_fcm_to_tokens(
    tokens: List[str],
    *,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> Tuple[List[str], List[str]]:
    """
    向多个 token 发送 FCM v1 消息。
    返回 (成功 tokens, 应删除的无效 tokens)。
    """
    if not tokens or not fcm_enabled():
        return [], []

    access = await _access_token()
    if not access:
        logger.warning("FCM v1: no access token")
        return [], []

    project = settings.FCM_PROJECT_ID
    url = f"https://fcm.googleapis.com/v1/projects/{project}/messages:send"
    headers = {"Authorization": f"Bearer {access}", "Content-Type": "application/json"}
    ok_tokens: List[str] = []
    stale_tokens: List[str] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        for token in tokens:
            payload: Dict[str, Any] = {
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                }
            }
            if data:
                payload["message"]["data"] = {k: str(v)[:512] for k, v in data.items()}

            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 200:
                    ok_tokens.append(token)
                    continue
                err_body = resp.json() if resp.content else {}
                err = err_body.get("error", {})
                status = err.get("status", "")
                if status in _INVALID_TOKEN_ERRORS or resp.status_code == 404:
                    stale_tokens.append(token)
                    logger.info("FCM stale token removed: %s (%s)", token[:16], status)
                else:
                    logger.warning("FCM send failed token=%s status=%s body=%s", token[:16], resp.status_code, resp.text[:200])
            except Exception as e:  # noqa: BLE001
                logger.warning("FCM send error token=%s: %s", token[:16], e)

    return ok_tokens, stale_tokens
