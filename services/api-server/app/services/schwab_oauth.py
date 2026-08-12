"""Schwab Trader API OAuth（对齐官方 Authorization Code 流程）。

官方授权链接格式（见 Authenticate with OAuth / 嘉信支持说明）：
  https://api.schwabapi.com/v1/oauth/authorize?client_id={APP_KEY}&redirect_uri={CALLBACK_URL}

回跳示例：
  https://127.0.0.1/?code=...&session=...
  或本站自动回流：{FRONTEND}/schwab/callback?code=...
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import unquote, urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_AUTHORIZE_URL = "https://api.schwabapi.com/v1/oauth/authorize"
_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"
_ACCOUNT_NUMBERS_URL = "https://api.schwabapi.com/trader/v1/accounts/accountNumbers"

# 须与 Developer Portal Callback URL 完全一致（常见兜底值）
_DEFAULT_REDIRECT_URI = "https://127.0.0.1"


def redirect_uri(override: str | None = None) -> str:
    raw = (override or settings.SCHWAB_OAUTH_REDIRECT_URI or _DEFAULT_REDIRECT_URI).strip()
    if len(raw) > 1 and raw.endswith("/"):
        raw = raw[:-1]
    return raw


def build_authorize_url(client_id: str, *, redirect: str | None = None) -> str:
    """只带官方要求的 client_id + redirect_uri（勿附加超长 state，易导致 LMS 异常）。"""
    params = urlencode(
        {
            "client_id": client_id.strip(),
            "redirect_uri": redirect_uri(redirect),
        }
    )
    return f"{_AUTHORIZE_URL}?{params}"


def parse_redirected_url(redirected_url: str) -> str:
    """从浏览器地址栏完整 URL 解析 authorization code。

    Schwab 的 code 常以 ``%40`` 结尾，换票前必须解码为 ``@``。
    """
    text = (redirected_url or "").strip()
    if not text:
        raise ValueError("empty redirected url")
    # 直接从原始串抓 code=，再 unquote 一次（避免 parse_qs 边界差异）
    match = re.search(r"[?&#]code=([^&#]+)", text)
    if not match:
        raise ValueError("redirected url missing code=...（请粘贴完整地址栏 URL）")
    code = unquote(match.group(1)).strip()
    if not code:
        raise ValueError("redirected url missing code=...（请粘贴完整地址栏 URL）")
    return code


def _format_token_error(response: httpx.Response) -> str:
    body = (response.text or "").strip()
    desc = body[:300] if body else "empty body"
    try:
        data = response.json()
        if isinstance(data, dict):
            desc = str(
                data.get("error_description")
                or data.get("error")
                or data.get("message")
                or desc
            ).strip()
    except Exception:  # noqa: BLE001
        pass
    low = desc.lower()
    if "expired" in low or "authorizationcode has expired" in low.replace(" ", ""):
        return f"authorization_code_expired ({response.status_code}): {desc}"
    if "invalid_client" in low or "unauthorized" in low:
        return f"invalid_client ({response.status_code}): {desc}"
    if "redirect" in low:
        return f"redirect_uri_mismatch ({response.status_code}): {desc}"
    return f"token_http_{response.status_code}: {desc}"


async def exchange_authorization_code(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect: str | None = None,
) -> Dict[str, Any]:
    redirect_value = redirect_uri(redirect)
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            _TOKEN_URL,
            auth=(client_id.strip(), client_secret.strip()),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_value,
            },
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        if response.status_code >= 400:
            detail = _format_token_error(response)
            logger.warning(
                "schwab token exchange failed redirect=%s detail=%s",
                redirect_value,
                detail[:300],
            )
            raise RuntimeError(detail)
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("token_response_invalid")
        return payload


async def fetch_account_numbers(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(
            _ACCOUNT_NUMBERS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "Accept-Encoding": "identity",
            },
        )
        if response.status_code >= 400:
            detail = _format_token_error(response)
            logger.warning("schwab accountNumbers failed: %s", detail[:300])
            raise RuntimeError(f"accountNumbers_failed: {detail}")
        payload = response.json()
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []


def pick_primary_account(rows: list[dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
    for row in rows:
        hash_value = str(row.get("hashValue") or "").strip()
        account_number = str(row.get("accountNumber") or "").strip()
        if hash_value:
            return hash_value, account_number or None
    return None, None
