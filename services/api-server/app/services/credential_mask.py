"""凭证展示用脱敏（不落库明文）。"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional


def mask_secret(value: str, visible: int = 4) -> str:
    raw = (value or "").strip()
    if not raw:
        return "—"
    if len(raw) <= visible * 2:
        return "••••••••"
    return f"{raw[:visible]}••••••••{raw[-visible:]}"


def mask_secret_prefix(value: str, visible: int = 2) -> str:
    """只展示前 N 位，不暴露尾部（用于 Consumer Key 等短标识）。"""
    raw = (value or "").strip()
    if not raw:
        return "—"
    return f"{raw[:visible]}••••••••"


def normalize_prefix_hint(hint: str, visible: int = 2) -> str:
    """把旧版「首尾各露」hint 收成只露前缀。"""
    raw = (hint or "").strip()
    if not raw or raw == "—":
        return "—"
    prefix = []
    for ch in raw:
        if ch == "•":
            break
        prefix.append(ch)
    text = "".join(prefix)
    if not text:
        return "••••••••"
    return mask_secret_prefix(text, visible)


def mask_encrypted_blob(ciphertext: Optional[str]) -> str:
    if not ciphertext:
        return "—"
    return mask_secret(ciphertext, 6)


def public_credential_row(cred) -> Dict[str, Any]:
    """BrokerCredential ORM -> 前端安全展示字段。"""
    cfg = dict(cred.config or {})
    broker = (cred.broker or "").lower()
    env = cfg.get("env") or ("production" if broker == "tiger" else "live")
    display_label = (getattr(cred, "label", None) or "").strip() or cfg.get("label") or cred.account_id or cred.broker
    row: Dict[str, Any] = {
        "id": str(cred.id),
        "broker": cred.broker,
        "account_id": cred.account_id or "",
        "label": display_label,
        "env": env,
        "license": cfg.get("license"),
        "tiger_id": cfg.get("tiger_id"),
        "has_private_key": bool(cred.private_key_encrypted),
        "has_secrets": bool(cred.secrets_encrypted),
        "key_hint": cfg.get("key_hint") or mask_encrypted_blob(cred.private_key_encrypted),
    }
    # 上次「测试账户」结果（净值/可用资金等，不含密钥）
    last_probe = cfg.get("last_probe")
    if isinstance(last_probe, dict):
        row["last_probe"] = {
            "ok": bool(last_probe.get("ok")),
            "tested_at": last_probe.get("tested_at"),
            "account_summary": last_probe.get("account_summary"),
            "error": last_probe.get("error"),
        }
    if broker == "tiger":
        if cfg.get("token_hint") or cred.secrets_encrypted:
            row["token_hint"] = cfg.get("token_hint") or "••••"
    elif broker == "longbridge":
        row["app_key_hint"] = cfg.get("app_key_hint") or "••••"
        row["app_secret_hint"] = cfg.get("app_secret_hint") or "••••"
        row["access_token_hint"] = cfg.get("access_token_hint") or "••••"
    elif broker == "schwab":
        row["client_id_hint"] = cfg.get("client_id_hint") or "••••"
        row["client_secret_hint"] = cfg.get("client_secret_hint") or "••••"
        row["oauth_status"] = cfg.get("oauth_status") or (
            "authorized" if cfg.get("refresh_token_hint") else "pending"
        )
        if cfg.get("oauth_redirect_uri"):
            row["oauth_redirect_uri"] = cfg.get("oauth_redirect_uri")
        if cfg.get("refresh_token_hint"):
            row["refresh_token_hint"] = cfg.get("refresh_token_hint")
        if cfg.get("account_hash_hint"):
            row["account_hash_hint"] = cfg.get("account_hash_hint")
    elif broker == "alpaca":
        row["api_key_hint"] = cfg.get("api_key_hint") or "••••"
        row["api_secret_hint"] = cfg.get("api_secret_hint") or "••••"
    elif broker == "ibkr_web":
        row["consumer_key_hint"] = normalize_prefix_hint(
            cfg.get("consumer_key_hint") or "••••", visible=2
        )
        row["access_token_hint"] = cfg.get("access_token_hint") or "••••"
    elif broker == "usmart":
        region = str(cfg.get("region") or "sg").strip().lower()
        if region in ("hk", "hongkong", "hong kong", "香港"):
            region = "hk"
        else:
            region = "sg"
        row["region"] = region
        row["channel"] = cfg.get("channel") or ""
        row["public_key_hint"] = cfg.get("public_key_hint") or "••••"
        row["private_key_hint"] = cfg.get("private_key_hint") or cfg.get("key_hint") or "••••"
        if cfg.get("phone_number_hint"):
            row["phone_number_hint"] = cfg.get("phone_number_hint")
    return row
