"""用户配置 API：路由规则、解析规则、通知、执行记录、急停。"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.utils.datetime import format_et
from app.deps import get_current_user, get_verified_user
from app.models import (
    AgentPresenceRow,
    ExecutionRecord,
    SignalSource,
    User,
    UserBrokerBinding,
    UserParseRule,
    UserRouteRule,
    UserSourceSubscription,
    WebhookIngestToken,
)
from app.services.entitlements import get_active_plan, has_feature, plan_features
from sigtrades_core.parse import apply_parse_rules, generate_parse_rule_from_example, parse_ai, summarize_generated_rule

router = APIRouter(prefix="/config", tags=["config"])


class RouteRuleUpsert(BaseModel):
    id: Optional[str] = None
    source_id: str
    action: str = "auto_trade"
    order_type_policy: str = "MKT_only"
    signal_subtype: Optional[str] = None
    broker: Optional[str] = None
    account_id: Optional[str] = None
    account_label: Optional[str] = None
    default_quantity: Optional[int] = None


class ParseRuleUpsert(BaseModel):
    source_id: str
    parse_mode: str = "example"
    priority: int = 0
    config: Dict[str, Any] = Field(default_factory=dict)
    label: str = "default"


class ParsePreviewRequest(BaseModel):
    sample: Any
    rules: Optional[List[ParseRuleUpsert]] = None
    source_id: Optional[str] = None
    author: Optional[str] = None
    option_default_dte: Optional[int] = Field(default=None, ge=0, le=90)


class ParseSourceSettingsUpsert(BaseModel):
    source_id: str
    option_default_dte: int = Field(default=0, ge=0, le=90)


class ParseGenerateRequest(BaseModel):
    sample: str
    expected_output: Dict[str, Any] = Field(default_factory=dict)


class ParseAiBootstrapRequest(BaseModel):
    sample: str
    author: Optional[str] = None
    prompt: Optional[str] = None


def _expected_output_from_ai_signal(signal: Dict[str, Any]) -> Dict[str, Any]:
    """将 AI 解析结果整理为 generate_parse_rule_from_example 所需的 expected_output。"""
    from sigtrades_core.parse.parser import sanitize_stock_vs_option

    signal = sanitize_stock_vs_option(dict(signal or {}))
    out: Dict[str, Any] = {}
    for key in ("action", "symbol", "quantity", "order_type", "signal_subtype", "asset_class", "limit_price"):
        if signal.get(key) is not None and signal.get(key) != "":
            out[key] = signal[key]
    meta = signal.get("metadata")
    if isinstance(meta, dict):
        # 正股不要带 strike/right，否则规则生成会走期权模板
        keys = ("underlying", "strike", "right", "expiry", "expiry_date", "dte")
        if str(out.get("asset_class") or "").upper() == "STOCK":
            keys = ("underlying",)
        clean = {k: v for k in keys if (v := meta.get(k)) is not None}
        if clean:
            out["metadata"] = clean
    if not out.get("asset_class") and out.get("symbol"):
        sym = str(out["symbol"]).strip().upper()
        # "SPY 590C" / OCC-like → OPTIONS；纯 ticker → STOCK
        out["asset_class"] = "OPTIONS" if (" " in sym or re.search(r"\d+[CP]$", sym)) else "STOCK"
    return out


class SourceSubscribeRequest(BaseModel):
    source_id: str
    enabled: bool = True


class KillSwitchRequest(BaseModel):
    enabled: bool


class DiscordSourceCreate(BaseModel):
    label: str = "My Discord"
    bot_token: str = Field(min_length=20)
    application_id: Optional[str] = None
    channel_ids: List[str] = Field(min_length=1)
    guild_id: Optional[str] = None
    action: str = "auto_trade"
    order_type_policy: str = "MKT_only"


class DiscordUserTokenRequest(BaseModel):
    user_token: str = Field(min_length=50)


class DiscordUserTokenOptionalRequest(BaseModel):
    user_token: Optional[str] = Field(default=None, min_length=50)


class DiscordUserGuildChannelsRequest(BaseModel):
    user_token: Optional[str] = Field(default=None, min_length=50)
    guild_id: str


class DiscordUserTestListenRequest(BaseModel):
    user_token: Optional[str] = Field(default=None, min_length=50)
    channel_ids: List[str] = Field(min_length=1)
    channel_labels: Optional[Dict[str, str]] = None


class DiscordBridgeSourceCreate(BaseModel):
    label: str = "My Discord"
    user_token: Optional[str] = Field(default=None, min_length=50)
    channel_ids: List[str] = Field(min_length=1)
    channel_labels: Optional[Dict[str, str]] = None
    guild_id: Optional[str] = None
    action: str = "auto_trade"
    order_type_policy: str = "MKT_only"


class DiscordBridgeSourceUpdate(BaseModel):
    label: Optional[str] = None
    channel_ids: Optional[List[str]] = None
    channel_labels: Optional[Dict[str, str]] = None
    guild_id: Optional[str] = None
    user_token: Optional[str] = Field(default=None, min_length=50)


class TelegramSourceCreate(BaseModel):
    label: str = "My Telegram"
    chat_ids: List[str] = Field(min_length=1)
    chat_labels: Optional[Dict[str, str]] = None
    action: str = "auto_trade"
    order_type_policy: str = "MKT_only"


class TelegramSourceUpdate(BaseModel):
    label: Optional[str] = None
    chat_ids: Optional[List[str]] = None
    chat_labels: Optional[Dict[str, str]] = None


class ParseRulesCopyRequest(BaseModel):
    from_source_id: str
    to_source_id: str


class RiskSettingsUpsert(BaseModel):
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    max_position_usd: Optional[float] = None
    max_daily_loss_usd: Optional[float] = None
    trading_hours: Dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


@router.get("/discord/oauth-url")
async def discord_oauth_url(user: User = Depends(get_current_user)):
    app_id = settings.DISCORD_APPLICATION_ID
    if not app_id:
        raise HTTPException(status_code=503, detail="DISCORD_APPLICATION_ID not configured")
    from app.security import create_state_token

    perms = settings.DISCORD_BOT_PERMISSIONS
    redirect_uri = quote(settings.DISCORD_OAUTH_REDIRECT_URI, safe="")
    # 签名 state：防止攻击者伪造 user.id 把 guild 绑到他人账户。
    state = quote(create_state_token({"sub": str(user.id)}), safe="")
    url = (
        f"https://discord.com/api/oauth2/authorize"
        f"?client_id={app_id}&permissions={perms}"
        f"&scope=bot%20applications.commands"
        f"&redirect_uri={redirect_uri}&response_type=code&state={state}"
    )
    return {
        "url": url,
        "redirect_uri": settings.DISCORD_OAUTH_REDIRECT_URI,
        "instructions": [
            "Create bot in Discord Developer Portal, enable Message Content Intent",
            "Invite bot to YOUR server (not the signal server)",
            "Follow announcement channels in Discord client → paste receiving channel IDs",
        ],
    }


@router.get("/discord/callback")
async def discord_oauth_callback(
    guild_id: Optional[str] = None,
    state: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Discord Bot OAuth 回调：记录 guild_id 到用户最近的 Discord 源。"""
    if guild_id and state:
        from app.security import decode_state_token

        payload = decode_state_token(state)
        if not payload or "sub" not in payload:
            return RedirectResponse(
                url=f"{settings.FRONTEND_URL}/app?discord=error&reason=invalid_state"
            )
        try:
            uid = uuid.UUID(payload["sub"])
            result = await db.execute(
                select(SignalSource)
                .where(SignalSource.kind == "discord", SignalSource.owner_user_id == uid)
                .order_by(SignalSource.source_id.desc())
            )
            src = result.scalars().first()
            if src:
                cfg = dict(src.config or {})
                cfg["guild_id"] = guild_id
                src.config = cfg
                await db.commit()
        except ValueError:
            pass
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/app?discord=connected&guild_id={guild_id or ''}"
    )


@router.get("/risk")
async def get_risk(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.models import UserRiskSettings

    result = await db.execute(select(UserRiskSettings).where(UserRiskSettings.user_id == user.id))
    row = result.scalar_one_or_none()
    if not row:
        return {"enabled": True, "trading_hours": {"tz": "America/New_York", "start": "09:30", "end": "16:00", "days": [0, 1, 2, 3, 4]}}
    return {
        "stop_loss_pct": row.stop_loss_pct,
        "take_profit_pct": row.take_profit_pct,
        "max_position_usd": row.max_position_usd,
        "max_daily_loss_usd": row.max_daily_loss_usd,
        "trading_hours": row.trading_hours,
        "enabled": row.enabled,
    }


@router.put("/risk")
async def put_risk(
    req: RiskSettingsUpsert,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models import UserRiskSettings

    result = await db.execute(select(UserRiskSettings).where(UserRiskSettings.user_id == user.id))
    row = result.scalar_one_or_none()
    if row is None:
        row = UserRiskSettings(user_id=user.id)
        db.add(row)
    row.stop_loss_pct = req.stop_loss_pct
    row.take_profit_pct = req.take_profit_pct
    row.max_position_usd = req.max_position_usd
    row.max_daily_loss_usd = req.max_daily_loss_usd
    row.trading_hours = req.trading_hours
    row.enabled = req.enabled
    await db.commit()
    return {"ok": True}


@router.get("/discord-sources")
async def list_discord_sources(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SignalSource)
        .where(
            SignalSource.kind == "discord",
            SignalSource.owner_user_id == user.id,
        )
        .order_by(SignalSource.source_id)
    )
    return [
        {
            "source_id": s.source_id,
            "name": s.name,
            "channel_ids": (s.config or {}).get("channel_ids", []),
            "channel_labels": (s.config or {}).get("channel_labels", {}),
            "guild_id": (s.config or {}).get("guild_id"),
            "application_id": (s.config or {}).get("application_id"),
            "has_bot_token": bool((s.config or {}).get("bot_token_encrypted")),
            "bridge_mode": (s.config or {}).get("bridge_mode", "bot"),
            "has_user_token": bool((s.config or {}).get("user_token_encrypted")),
            "user_token_hint": (s.config or {}).get("user_token_hint"),
            "discord_username": (s.config or {}).get("discord_username"),
            "is_active": s.is_active,
            "option_default_dte": int((s.config or {}).get("option_default_dte", 0)),
        }
        for s in result.scalars().all()
    ]


async def _count_user_sources(db: AsyncSession, user_id) -> int:
    from sqlalchemy import func as _func

    result = await db.execute(
        select(_func.count()).select_from(SignalSource).where(SignalSource.owner_user_id == user_id)
    )
    return result.scalar() or 0


@router.post("/discord-source")
async def create_discord_source(
    req: DiscordSourceCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.crypto import encrypt
    from app.services.entitlements import ensure_within_limit

    await ensure_within_limit(
        db, user.id, "max_signal_sources", await _count_user_sources(db, user.id), default=1
    )
    bot_token = req.bot_token.strip()
    if not bot_token:
        raise HTTPException(status_code=400, detail="bot_token required")

    source_id = f"dc-{uuid.uuid4().hex[:12]}"
    existing = await db.execute(select(SignalSource).where(SignalSource.source_id == source_id))
    if existing.scalar_one_or_none() is None:
        db.add(SignalSource(
            source_id=source_id,
            kind="discord",
            ownership="user_private",
            owner_user_id=user.id,
            name=req.label,
            config={
                "channel_ids": [str(c).strip() for c in req.channel_ids if str(c).strip()],
                "guild_id": req.guild_id,
                "application_id": (req.application_id or "").strip() or None,
                "bot_token_encrypted": encrypt(bot_token),
            },
        ))
    await db.commit()
    return {"source_id": source_id, "channel_ids": req.channel_ids, "has_bot_token": True}


def _discord_token_hint(token: str) -> str:
    t = token.strip()
    if len(t) <= 8:
        return "****"
    return f"{t[:4]}{'•' * 16}{t[-4:]}"


async def _list_personal_discord_sources(db: AsyncSession, user_id: uuid.UUID) -> List[SignalSource]:
    result = await db.execute(
        select(SignalSource)
        .where(
            SignalSource.kind == "discord",
            SignalSource.owner_user_id == user_id,
        )
        .order_by(SignalSource.source_id)
    )
    return [s for s in result.scalars().all() if (s.config or {}).get("bridge_mode") == "personal"]


async def _find_personal_discord_source(db: AsyncSession, user_id: uuid.UUID) -> Optional[SignalSource]:
    sources = await _list_personal_discord_sources(db, user_id)
    return sources[0] if sources else None


async def _load_stored_discord_user_token(db: AsyncSession, user_id: uuid.UUID) -> Optional[str]:
    from app.services.crypto import decrypt

    for src in await _list_personal_discord_sources(db, user_id):
        enc = (src.config or {}).get("user_token_encrypted")
        if not enc:
            continue
        try:
            return decrypt(enc)
        except Exception:  # noqa: BLE001
            continue
    return None


def _apply_discord_token_to_config(cfg: dict, token: str, username: str) -> dict:
    from app.services.crypto import encrypt

    next_cfg = dict(cfg)
    next_cfg["user_token_encrypted"] = encrypt(token)
    next_cfg["user_token_hint"] = _discord_token_hint(token)
    if username:
        next_cfg["discord_username"] = username
    next_cfg["bridge_mode"] = "personal"
    return next_cfg


async def _resolve_discord_user_token(
    db: AsyncSession, user_id: uuid.UUID, provided: Optional[str]
) -> str:
    if provided and provided.strip():
        return provided.strip()
    token = await _load_stored_discord_user_token(db, user_id)
    if not token:
        raise HTTPException(status_code=400, detail="discord_token_required")
    return token


@router.get("/discord-user/token-status")
async def discord_user_token_status(
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    src = await _find_personal_discord_source(db, user.id)
    if not src:
        return {"saved": False}
    cfg = src.config or {}
    if not cfg.get("user_token_encrypted"):
        return {"saved": False}
    hint = cfg.get("user_token_hint")
    if not hint:
        stored = await _load_stored_discord_user_token(db, user.id)
        if stored:
            hint = _discord_token_hint(stored)
            cfg = dict(cfg)
            cfg["user_token_hint"] = hint
            src.config = cfg
            await db.commit()
    return {
        "saved": True,
        "hint": hint or "****",
        "user": cfg.get("discord_username") or "",
        "source_id": src.source_id,
        "is_active": src.is_active,
    }


@router.post("/discord-user/save-token")
async def discord_user_save_token(
    req: DiscordUserTokenRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.discord_user_api import validate_user_token

    token = req.user_token.strip()
    try:
        profile = await validate_user_token(token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    username = profile.get("global_name") or profile.get("username") or ""
    hint = _discord_token_hint(token)
    personal_sources = await _list_personal_discord_sources(db, user.id)

    if personal_sources:
        for src in personal_sources:
            src.config = _apply_discord_token_to_config(src.config or {}, token, username)
    else:
        source_id = f"dc-{uuid.uuid4().hex[:12]}"
        db.add(SignalSource(
            source_id=source_id,
            kind="discord",
            ownership="user_private",
            owner_user_id=user.id,
            name="My Discord",
            is_active=False,
            config=_apply_discord_token_to_config(
                {"channel_ids": [], "channel_labels": {}},
                token,
                username,
            ),
        ))
    await db.commit()
    return {"ok": True, "hint": hint, "user": username}


@router.post("/discord-user/validate")
async def discord_user_validate(req: DiscordUserTokenRequest, user: User = Depends(get_verified_user)):
    from app.services.discord_user_api import validate_user_token

    try:
        profile = await validate_user_token(req.user_token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "user": profile}


_DISCORD_ICON_SIZES = (16, 32, 64, 128, 256, 512, 1024, 2048, 4096)


def _normalize_discord_icon_size(size: int) -> int:
    clamped = max(16, min(int(size), 4096))
    for allowed in _DISCORD_ICON_SIZES:
        if allowed >= clamped:
            return allowed
    return 4096


@router.get("/discord-asset/guild-icon")
async def discord_guild_icon_asset(guild_id: str, icon: str, size: int = 64):
    """代理 Discord 服务器图标，避免浏览器直连 CDN 失败。"""
    import httpx

    from app.services.discord_user_api import guild_icon_cdn_urls

    if not guild_id or not icon:
        raise HTTPException(status_code=400, detail="guild_id and icon required")
    size = _normalize_discord_icon_size(size)
    async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
        for url in guild_icon_cdn_urls(guild_id, icon, size):
            resp = await client.get(url)
            if resp.status_code == 200 and resp.content:
                media_type = resp.headers.get("content-type", "image/png")
                return Response(
                    content=resp.content,
                    media_type=media_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
    raise HTTPException(status_code=404, detail="guild icon not found")


@router.post("/discord-user/guilds")
async def discord_user_guilds(
    req: DiscordUserTokenOptionalRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.discord_user_api import fetch_guilds

    token = await _resolve_discord_user_token(db, user.id, req.user_token)
    try:
        guilds = await fetch_guilds(token)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"guilds": guilds}


@router.post("/discord-user/channels")
async def discord_user_channels(
    req: DiscordUserGuildChannelsRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.discord_user_api import fetch_guild_channels

    token = await _resolve_discord_user_token(db, user.id, req.user_token)
    try:
        channels = await fetch_guild_channels(token, req.guild_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"channels": channels}


@router.post("/discord-user/test-listen")
async def discord_user_test_listen(
    req: DiscordUserTestListenRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    import httpx

    from app.config import settings

    token = await _resolve_discord_user_token(db, user.id, req.user_token)
    channel_ids = [str(c).strip() for c in req.channel_ids if str(c).strip()]
    async with httpx.AsyncClient(trust_env=False, timeout=15.0) as client:
        resp = await client.post(
            f"{settings.INGEST_URL}/internal/discord-user/test-listen",
            json={
                "user_token": token,
                "channel_ids": channel_ids,
                "channel_labels": req.channel_labels or {},
            },
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
        )
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.post("/discord-user/test-stop")
async def discord_user_test_stop(session_id: str, user: User = Depends(get_verified_user)):
    import httpx

    from app.config import settings

    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.post(
            f"{settings.INGEST_URL}/internal/discord-user/test-stop",
            json={"session_id": session_id},
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
        )
    resp.raise_for_status()
    return resp.json()


@router.get("/discord-user/test-messages")
async def discord_user_test_messages(session_id: str, user: User = Depends(get_verified_user)):
    import httpx

    from app.config import settings

    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.get(
            f"{settings.INGEST_URL}/internal/discord-user/test-messages",
            params={"session_id": session_id},
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
        )
    resp.raise_for_status()
    return resp.json()


@router.get("/discord-user/preview-messages/{source_id}")
async def discord_user_preview_messages(source_id: str, user: User = Depends(get_verified_user), db: AsyncSession = Depends(get_db)):
    import httpx

    from app.config import settings

    owned = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.owner_user_id == user.id,
            SignalSource.kind == "discord",
        )
    )
    if owned.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="source not found")
    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.get(
            f"{settings.INGEST_URL}/internal/discord-user/preview/{source_id}",
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
        )
    resp.raise_for_status()
    return resp.json()


@router.post("/discord-bridge-source")
async def create_discord_bridge_source(
    req: DiscordBridgeSourceCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.crypto import encrypt

    from app.services.entitlements import ensure_discord_channels, ensure_within_limit

    channel_ids = [str(c).strip() for c in req.channel_ids if str(c).strip()]
    if not channel_ids:
        raise HTTPException(status_code=400, detail="channel_ids required")
    await ensure_within_limit(
        db, user.id, "max_signal_sources", await _count_user_sources(db, user.id), default=1
    )
    await ensure_discord_channels(db, user.id, len(channel_ids))
    user_token = await _resolve_discord_user_token(db, user.id, req.user_token)
    discord_username = ""
    for src in await _list_personal_discord_sources(db, user.id):
        discord_username = (src.config or {}).get("discord_username") or discord_username

    bridge_config = {
        "bridge_mode": "personal",
        "channel_ids": channel_ids,
        "channel_labels": req.channel_labels or {},
        "guild_id": req.guild_id,
        "user_token_encrypted": encrypt(user_token),
        "user_token_hint": _discord_token_hint(user_token),
        "discord_username": discord_username,
    }

    # 只创建信号源；流水线关联（UserRouteRule）在向导最后一步 PUT /route-rules 时建立。
    source_id = f"dc-{uuid.uuid4().hex[:12]}"
    db.add(SignalSource(
        source_id=source_id,
        kind="discord",
        ownership="user_private",
        owner_user_id=user.id,
        name=req.label,
        config=bridge_config,
    ))
    await db.commit()
    return {
        "source_id": source_id,
        "channel_ids": channel_ids,
        "bridge_mode": "personal",
        "updated": False,
    }


@router.patch("/discord-bridge-source/{source_id}")
async def update_discord_bridge_source(
    source_id: str,
    req: DiscordBridgeSourceUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.crypto import encrypt

    result = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.kind == "discord",
            SignalSource.owner_user_id == user.id,
        )
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    cfg = dict(src.config or {})
    if cfg.get("bridge_mode") != "personal":
        raise HTTPException(status_code=400, detail="not a personal discord source")

    if req.label is not None:
        src.name = req.label.strip() or src.name
    if req.channel_ids is not None:
        channel_ids = [str(c).strip() for c in req.channel_ids if str(c).strip()]
        if not channel_ids:
            raise HTTPException(status_code=400, detail="channel_ids required")
        from app.services.entitlements import ensure_discord_channels

        await ensure_discord_channels(db, user.id, len(channel_ids))
        cfg["channel_ids"] = channel_ids
    if req.channel_labels is not None:
        cfg["channel_labels"] = req.channel_labels
    if req.guild_id is not None:
        cfg["guild_id"] = req.guild_id
    if req.user_token:
        token = req.user_token.strip()
        cfg["user_token_encrypted"] = encrypt(token)
        cfg["user_token_hint"] = _discord_token_hint(token)

    cfg["bridge_mode"] = "personal"
    src.config = cfg
    src.is_active = True
    await db.commit()
    return {
        "source_id": src.source_id,
        "channel_ids": cfg.get("channel_ids", []),
        "bridge_mode": "personal",
        "updated": True,
    }


@router.post("/discord-bridge-source/{source_id}/stop")
async def stop_discord_bridge_source(
    source_id: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.kind == "discord",
            SignalSource.owner_user_id == user.id,
        )
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    cfg = src.config or {}
    if cfg.get("bridge_mode") != "personal":
        raise HTTPException(status_code=400, detail="not a personal discord source")

    src.is_active = False
    await db.commit()
    return {"ok": True, "source_id": source_id}


async def _delete_user_source(db: AsyncSession, user_id: uuid.UUID, source_id: str) -> SignalSource:
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.owner_user_id == user_id,
        )
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")

    await db.execute(
        delete(UserParseRule).where(
            UserParseRule.user_id == user_id,
            UserParseRule.source_id == source_id,
        )
    )
    await db.execute(
        delete(UserRouteRule).where(
            UserRouteRule.user_id == user_id,
            UserRouteRule.source_id == source_id,
        )
    )
    await db.execute(
        delete(UserSourceSubscription).where(
            UserSourceSubscription.user_id == user_id,
            UserSourceSubscription.source_id == source_id,
        )
    )
    await db.execute(
        delete(WebhookIngestToken).where(
            WebhookIngestToken.user_id == user_id,
            WebhookIngestToken.source_id == source_id,
        )
    )
    await db.delete(src)
    return src


@router.delete("/sources/{source_id}")
async def delete_user_source(
    source_id: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    await _delete_user_source(db, user.id, source_id)
    await db.commit()
    return {"ok": True, "source_id": source_id}


@router.delete("/webhooks/{token}")
async def delete_webhook(
    token: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WebhookIngestToken).where(
            WebhookIngestToken.user_id == user.id,
            WebhookIngestToken.token == token,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="webhook not found")
    source_id = row.source_id
    await db.delete(row)
    remaining = (await db.execute(
        select(WebhookIngestToken).where(
            WebhookIngestToken.user_id == user.id,
            WebhookIngestToken.source_id == source_id,
        )
    )).scalars().first()
    if remaining is None:
        try:
            await _delete_user_source(db, user.id, source_id)
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    await db.commit()
    return {"ok": True, "source_id": source_id}


@router.delete("/pipelines/{source_id}")
async def delete_pipeline(
    source_id: str,
    rule_id: Optional[str] = None,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """解除流水线关联（UserRouteRule），不删除信号源 / Discord token / 解析规则。"""
    if rule_id:
        try:
            rid = uuid.UUID(rule_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid rule_id") from exc
        rule = (await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.id == rid,
                UserRouteRule.user_id == user.id,
                UserRouteRule.source_id == source_id,
            )
        )).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="route rule not found")
        await db.delete(rule)
        await db.commit()
        return {"ok": True, "source_id": source_id, "rule_id": rule_id}

    rules = (await db.execute(
        select(UserRouteRule).where(
            UserRouteRule.user_id == user.id,
            UserRouteRule.source_id == source_id,
        )
    )).scalars().all()
    if not rules:
        raise HTTPException(status_code=404, detail="pipeline not found")
    for rule in rules:
        await db.delete(rule)
    await db.commit()
    return {"ok": True, "source_id": source_id, "unlinked": len(rules)}


@router.post("/pipelines/{rule_id}/pause")
async def pause_pipeline(
    rule_id: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rid = uuid.UUID(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid rule_id") from exc
    rule = (await db.execute(
        select(UserRouteRule).where(
            UserRouteRule.id == rid,
            UserRouteRule.user_id == user.id,
        )
    )).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    rule.is_active = False
    await db.commit()
    return {"ok": True, "rule_id": rule_id, "is_active": False}


@router.post("/pipelines/{rule_id}/resume")
async def resume_pipeline(
    rule_id: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        rid = uuid.UUID(rule_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid rule_id") from exc
    rule = (await db.execute(
        select(UserRouteRule).where(
            UserRouteRule.id == rid,
            UserRouteRule.user_id == user.id,
        )
    )).scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="pipeline not found")
    rule.is_active = True
    await db.commit()
    return {"ok": True, "rule_id": rule_id, "is_active": True}


@router.get("/telegram-sources")
async def list_telegram_sources(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.kind == "telegram",
            SignalSource.owner_user_id == user.id,
        )
    )
    return [
        {
            "source_id": s.source_id,
            "name": s.name,
            "chat_ids": (s.config or {}).get("chat_ids") or [],
            "chat_labels": (s.config or {}).get("chat_labels") or {},
            "is_active": s.is_active,
            "kind": "telegram",
        }
        for s in result.scalars().all()
    ]


@router.post("/telegram-source")
async def create_telegram_source(
    req: TelegramSourceCreate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.entitlements import ensure_within_limit

    await ensure_within_limit(
        db, user.id, "max_signal_sources", await _count_user_sources(db, user.id), default=1
    )
    chat_ids = [str(c).strip() for c in req.chat_ids if str(c).strip()]
    if not chat_ids:
        raise HTTPException(status_code=400, detail="chat_ids required")
    source_id = f"tg-{uuid.uuid4().hex[:12]}"
    db.add(SignalSource(
        source_id=source_id,
        kind="telegram",
        ownership="user_private",
        owner_user_id=user.id,
        name=req.label.strip() or "My Telegram",
        config={
            "chat_ids": chat_ids,
            "chat_labels": req.chat_labels or {},
        },
    ))
    await db.commit()
    return {"source_id": source_id, "chat_ids": chat_ids}


@router.patch("/telegram-source/{source_id}")
async def update_telegram_source(
    source_id: str,
    req: TelegramSourceUpdate,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.kind == "telegram",
            SignalSource.owner_user_id == user.id,
        )
    )
    src = result.scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    cfg = dict(src.config or {})
    if req.label is not None:
        src.name = req.label.strip() or src.name
    if req.chat_ids is not None:
        chat_ids = [str(c).strip() for c in req.chat_ids if str(c).strip()]
        if not chat_ids:
            raise HTTPException(status_code=400, detail="chat_ids required")
        cfg["chat_ids"] = chat_ids
    if req.chat_labels is not None:
        cfg["chat_labels"] = req.chat_labels
    src.config = cfg
    await db.commit()
    return {
        "source_id": source_id,
        "name": src.name,
        "chat_ids": cfg.get("chat_ids") or [],
    }


@router.get("/route-rules")
async def list_route_rules(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserRouteRule).where(UserRouteRule.user_id == user.id))
    return [
        {
            "id": str(r.id),
            "source_id": r.source_id,
            "action": r.action,
            "order_type_policy": r.order_type_policy,
            "signal_subtype": r.signal_subtype,
            "broker": r.broker,
            "account_id": r.account_id,
            "account_label": r.account_label,
            "default_quantity": r.default_quantity,
            "is_active": r.is_active,
        }
        for r in result.scalars().all()
    ]


@router.put("/route-rules")
async def upsert_route_rule(
    req: RouteRuleUpsert,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    rule: Optional[UserRouteRule] = None
    if req.id:
        try:
            rid = uuid.UUID(req.id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid rule id") from exc
        rule = (await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.id == rid,
                UserRouteRule.user_id == user.id,
                UserRouteRule.source_id == req.source_id,
            )
        )).scalar_one_or_none()
        if rule is None:
            raise HTTPException(status_code=404, detail="route rule not found")
    elif req.broker:
        q = select(UserRouteRule).where(
            UserRouteRule.user_id == user.id,
            UserRouteRule.source_id == req.source_id,
            UserRouteRule.broker == req.broker,
        )
        label = (req.account_label or "").strip()
        if label:
            q = q.where(UserRouteRule.account_label == label)
        elif req.account_id:
            q = q.where(UserRouteRule.account_id == req.account_id)
        rule = (await db.execute(q)).scalar_one_or_none()
        if rule is None:
            orphan_rules = (await db.execute(
                select(UserRouteRule).where(
                    UserRouteRule.user_id == user.id,
                    UserRouteRule.source_id == req.source_id,
                    UserRouteRule.broker.is_(None),
                )
            )).scalars().all()
            if len(orphan_rules) == 1:
                rule = orphan_rules[0]
    else:
        rules = (await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.user_id == user.id,
                UserRouteRule.source_id == req.source_id,
            )
        )).scalars().all()
        if len(rules) == 1 and not rules[0].broker:
            rule = rules[0]

    if rule is None:
        dup_q = select(UserRouteRule).where(
            UserRouteRule.user_id == user.id,
            UserRouteRule.source_id == req.source_id,
        )
        if req.broker:
            dup_q = dup_q.where(UserRouteRule.broker == req.broker)
            label = (req.account_label or "").strip()
            if label:
                dup_q = dup_q.where(UserRouteRule.account_label == label)
            elif req.account_id:
                dup_q = dup_q.where(UserRouteRule.account_id == req.account_id)
        dup_rules = (await db.execute(dup_q)).scalars().all()
        if len(dup_rules) >= 1:
            rule = dup_rules[0]
        else:
            existing = (await db.execute(
                select(UserRouteRule).where(
                    UserRouteRule.user_id == user.id,
                    UserRouteRule.source_id == req.source_id,
                )
            )).scalars().all()
            if any(r.broker for r in existing):
                raise HTTPException(
                    status_code=409,
                    detail="pipeline already exists for this source; create a new pipeline instead",
                )

    if rule is None:
        rule = UserRouteRule(user_id=user.id, source_id=req.source_id)
        db.add(rule)

    action = (req.action or "").strip()
    if action in ("auto_trade", "both") and not await has_feature(db, user.id, "auto_trade"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "plan_feature_required",
                "feature": "auto_trade",
                "message": "plan_no_auto_trade",
            },
        )

    rule.action = action or req.action
    rule.order_type_policy = req.order_type_policy
    rule.signal_subtype = req.signal_subtype
    if req.broker is not None:
        rule.broker = req.broker or None
    if req.account_id is not None:
        rule.account_id = req.account_id or None
    if req.account_label is not None:
        rule.account_label = req.account_label or None
    payload = req.model_dump(exclude_unset=True)
    if "default_quantity" in payload:
        dq = payload["default_quantity"]
        rule.default_quantity = dq if (dq and dq > 0) else None

    await db.commit()
    return {"ok": True, "id": str(rule.id)}


async def _owned_signal_source(
    db: AsyncSession,
    user_id: uuid.UUID,
    source_id: str,
) -> Optional[SignalSource]:
    result = await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == source_id,
            SignalSource.owner_user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def _source_option_default_dte(db: AsyncSession, user_id: uuid.UUID, source_id: str) -> int:
    src = await _owned_signal_source(db, user_id, source_id)
    if src is None:
        return 0
    return int((src.config or {}).get("option_default_dte", 0))


@router.get("/parse-source-settings/{source_id}")
async def get_parse_source_settings(
    source_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    src = await _owned_signal_source(db, user.id, source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    return {"option_default_dte": int((src.config or {}).get("option_default_dte", 0))}


@router.put("/parse-source-settings")
async def upsert_parse_source_settings(
    req: ParseSourceSettingsUpsert,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    src = await _owned_signal_source(db, user.id, req.source_id)
    if src is None:
        raise HTTPException(status_code=404, detail="source not found")
    cfg = dict(src.config or {})
    cfg["option_default_dte"] = req.option_default_dte
    src.config = cfg
    await db.commit()
    return {"ok": True, "option_default_dte": req.option_default_dte}


@router.get("/parse-rules")
async def list_parse_rules(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(UserParseRule).where(UserParseRule.user_id == user.id))
    return [
        {
            "id": str(r.id),
            "source_id": r.source_id,
            "parse_mode": r.parse_mode,
            "priority": r.priority,
            "config": r.config,
            "label": r.label,
        }
        for r in result.scalars().all()
    ]


@router.put("/parse-rules")
async def upsert_parse_rule(
    req: ParseRuleUpsert,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserParseRule).where(
            UserParseRule.user_id == user.id,
            UserParseRule.source_id == req.source_id,
            UserParseRule.label == req.label,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        rule = UserParseRule(user_id=user.id, source_id=req.source_id, label=req.label)
        db.add(rule)
    rule.parse_mode = req.parse_mode
    rule.priority = req.priority
    rule.config = req.config
    await db.commit()
    return {"ok": True, "id": str(rule.id)}


@router.post("/parse-rules/copy")
async def copy_parse_rules(
    req: ParseRulesCopyRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """将 from_source 的解析规则复制到 to_source（同 parse_mode/config，不同 source_id）。

    Discord / Telegram 共用同一套解析引擎；规则按 source_id 存储，复制后两边独立维护。
    """
    from_id = req.from_source_id.strip()
    to_id = req.to_source_id.strip()
    if not from_id or not to_id:
        raise HTTPException(status_code=400, detail="from_source_id and to_source_id required")
    if from_id == to_id:
        raise HTTPException(status_code=400, detail="from and to source must differ")

    # 确认目标源属于当前用户（Discord / Telegram / Webhook）
    to_src = (await db.execute(
        select(SignalSource).where(
            SignalSource.source_id == to_id,
            SignalSource.owner_user_id == user.id,
        )
    )).scalar_one_or_none()
    if to_src is None:
        raise HTTPException(status_code=404, detail="target source not found")

    from_rules = (await db.execute(
        select(UserParseRule).where(
            UserParseRule.user_id == user.id,
            UserParseRule.source_id == from_id,
        )
    )).scalars().all()
    if not from_rules:
        raise HTTPException(status_code=404, detail="no parse rules on source")

    copied = 0
    for src_rule in from_rules:
        existing = (await db.execute(
            select(UserParseRule).where(
                UserParseRule.user_id == user.id,
                UserParseRule.source_id == to_id,
                UserParseRule.label == src_rule.label,
            )
        )).scalar_one_or_none()
        if existing is None:
            existing = UserParseRule(
                user_id=user.id,
                source_id=to_id,
                label=src_rule.label,
            )
            db.add(existing)
        existing.parse_mode = src_rule.parse_mode
        existing.priority = src_rule.priority
        existing.config = dict(src_rule.config or {})
        copied += 1
    await db.commit()
    return {"ok": True, "copied": copied, "to_source_id": to_id}


@router.delete("/parse-rules")
async def delete_parse_rule(
    source_id: str,
    label: str,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserParseRule).where(
            UserParseRule.user_id == user.id,
            UserParseRule.source_id == source_id,
            UserParseRule.label == label,
        )
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=404, detail="parse rule not found")
    await db.delete(rule)
    await db.commit()
    return {"ok": True}


@router.post("/parse-generate-rule")
async def parse_generate_rule(
    req: ParseGenerateRequest,
    user: User = Depends(get_verified_user),
):
    try:
        config = generate_parse_rule_from_example(req.sample.strip(), req.expected_output)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    preview = await apply_parse_rules(req.sample.strip(), [{"parse_mode": "example", "config": config}])
    return {
        "parse_mode": "example",
        "config": config,
        "summary": summarize_generated_rule(config),
        "preview": {
            "signal": preview.signal,
            "confidence": preview.confidence,
            "mode": preview.mode,
            "error": preview.error,
        },
    }


@router.post("/parse-ai-bootstrap")
async def parse_ai_bootstrap(
    req: ParseAiBootstrapRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """AI 解析样例 → 生成 example/正则规则配置（供向导一键保存）。"""
    sample = req.sample.strip()
    if not sample:
        raise HTTPException(status_code=400, detail="sample is required")

    ai_kwargs = settings.ai_parse_kwargs()
    if not ai_kwargs.get("openai_api_key"):
        raise HTTPException(
            status_code=400,
            detail={"error": "ai_not_configured", "message": "AI_API_KEY / OPENAI_API_KEY not configured"},
        )
    if not await has_feature(db, user.id, "ai_parse"):
        raise HTTPException(
            status_code=403,
            detail={"error": "plan_feature_required", "feature": "ai_parse"},
        )

    ai_result = await parse_ai(
        sample,
        req.prompt,
        ai_kwargs.get("openai_api_key"),
        base_url=ai_kwargs.get("openai_base_url"),
        model=ai_kwargs.get("openai_model"),
        max_tokens=int(ai_kwargs.get("openai_max_tokens") or 2000),
        timeout=float(ai_kwargs.get("openai_timeout") or 30),
    )
    if ai_result.error and ai_result.mode == "ai_fallback":
        raise HTTPException(
            status_code=400,
            detail={"error": "ai_parse_failed", "message": ai_result.error},
        )
    action = str(ai_result.signal.get("action") or "").strip()
    symbol = str(ai_result.signal.get("symbol") or "").strip()
    if not action or not symbol:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "ai_parse_incomplete",
                "message": "AI could not extract action/symbol",
                "signal": ai_result.signal,
                "mode": ai_result.mode,
            },
        )

    expected = _expected_output_from_ai_signal(ai_result.signal)
    try:
        config = generate_parse_rule_from_example(sample, expected)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={"error": "rule_generate_failed", "message": str(e), "ai_signal": ai_result.signal},
        ) from e

    preview = await apply_parse_rules(
        sample,
        [{"parse_mode": "example", "config": config}],
        allow_ai=False,
    )
    return {
        "ai": {
            "signal": ai_result.signal,
            "confidence": ai_result.confidence,
            "mode": ai_result.mode,
            "error": ai_result.error,
        },
        "expected_output": expected,
        "parse_mode": "example",
        "config": config,
        "summary": summarize_generated_rule(config),
        "preview": {
            "signal": preview.signal,
            "confidence": preview.confidence,
            "mode": preview.mode,
            "error": preview.error,
        },
    }


@router.post("/parse-preview")
async def parse_preview(
    req: ParsePreviewRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    rules_payload: List[Dict[str, Any]] = []
    if req.rules:
        rules_payload = [r.model_dump() for r in req.rules]
    elif req.source_id:
        result = await db.execute(
            select(UserParseRule).where(
                UserParseRule.user_id == user.id,
                UserParseRule.source_id == req.source_id,
            )
        )
        rules_payload = [
            {
                "parse_mode": r.parse_mode,
                "priority": r.priority,
                "config": r.config,
                "label": r.label,
            }
            for r in result.scalars().all()
        ]
    sample = req.sample
    if req.author and isinstance(sample, str):
        sample = {"raw_text": sample, "author": req.author.strip()}
    elif req.author and isinstance(sample, dict):
        sample = {**sample, "author": req.author.strip()}

    option_default_dte = req.option_default_dte
    if option_default_dte is None and req.source_id:
        option_default_dte = await _source_option_default_dte(db, user.id, req.source_id)

    allow_ai = await has_feature(db, user.id, "ai_parse")
    result = await apply_parse_rules(
        sample,
        rules_payload,
        allow_ai=allow_ai,
        option_default_dte=option_default_dte,
        **settings.ai_parse_kwargs(),
    )
    return {
        "signal": result.signal,
        "confidence": result.confidence,
        "mode": result.mode,
        "error": result.error,
        "matched_label": result.matched_label,
    }


@router.get("/webhooks")
async def list_webhooks(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(WebhookIngestToken).where(WebhookIngestToken.user_id == user.id))
    return [
        {"token": w.token, "source_id": w.source_id, "label": w.label, "url_path": f"/ingest/wh/{w.token}"}
        for w in result.scalars().all()
    ]


@router.get("/sources/platform")
async def list_platform_sources(db: AsyncSession = Depends(get_db)):
    from app.services.seed import DEMO_PLATFORM_SOURCE_ID

    result = await db.execute(
        select(SignalSource).where(
            SignalSource.ownership == "platform_shared",
            SignalSource.is_active.is_(True),
            SignalSource.source_id != DEMO_PLATFORM_SOURCE_ID,
        )
    )
    return [
        {"source_id": s.source_id, "name": s.name, "kind": s.kind}
        for s in result.scalars().all()
    ]


@router.post("/sources/subscribe")
async def subscribe_source(
    req: SourceSubscribeRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserSourceSubscription).where(
            UserSourceSubscription.user_id == user.id,
            UserSourceSubscription.source_id == req.source_id,
        )
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        sub = UserSourceSubscription(user_id=user.id, source_id=req.source_id)
        db.add(sub)
    sub.enabled = req.enabled
    await db.commit()
    return {"ok": True}


class ExecutionActionRequest(BaseModel):
    source_id: str
    account_label: Optional[str] = None


EXECUTION_SYNC_TIMEOUT_SEC = 60
_STALE_EXEC_STATUSES = frozenset({"UNKNOWN", "PENDING", "SUBMITTED", "NEW", "ROUTING", "DISPATCHED"})


def _parse_order_id_from_detail(detail: Optional[str], order_id: Optional[str] = None) -> Optional[str]:
    if order_id:
        return str(order_id)
    if not detail:
        return None
    import re

    match = re.search(r"order=([^;\s]+)", detail, re.I)
    return match.group(1) if match else None


def _parse_attempt_from_detail(detail: Optional[str]) -> Optional[int]:
    if not detail:
        return None
    import re

    match = re.search(r"(?:^|;\s*)attempt=(\d+)", detail, re.I)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _execution_sync_timed_out(record: ExecutionRecord, status: str, order_id: Optional[str]) -> bool:
    if status not in _STALE_EXEC_STATUSES:
        return False
    created = record.created_at
    if not created:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - created).total_seconds()
    if age < EXECUTION_SYNC_TIMEOUT_SEC:
        return False
    return bool(order_id) or status in _STALE_EXEC_STATUSES


@router.get("/executions")
async def list_executions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    source_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    from app.models import ExecutionReportRow
    from sqlalchemy import func

    limit = max(1, min(limit, 200))
    offset = max(0, offset)

    filters = [ExecutionRecord.user_id == user.id]
    if source_id:
        filters.append(ExecutionRecord.source_id == source_id)

    total = (await db.execute(
        select(func.count()).select_from(ExecutionRecord).where(*filters)
    )).scalar_one() or 0

    query = (
        select(ExecutionRecord)
        .where(*filters)
        .order_by(ExecutionRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(query)
    records = result.scalars().all()

    # 批量取最新成交回报，补充成交价/已实现盈亏（供前端展示真实结果）。
    signal_ids = [r.signal_id for r in records]
    reports: dict[str, ExecutionReportRow] = {}
    if signal_ids:
        rep_rows = (await db.execute(
            select(ExecutionReportRow)
            .where(
                ExecutionReportRow.user_id == user.id,
                ExecutionReportRow.signal_id.in_(signal_ids),
            )
            .order_by(ExecutionReportRow.created_at.desc())
        )).scalars().all()
        for rep in rep_rows:
            key = f"{rep.signal_id}:{rep.account_id or '_'}"
            if key not in reports:
                reports[key] = rep

    out = []
    for e in records:
        rep = reports.get(f"{e.signal_id}:{e.account_id or '_'}")
        payload = rep.payload if rep else {}
        account_label = e.account_label
        if not account_label and e.detail:
            try:
                detail_obj = json.loads(e.detail)
                if isinstance(detail_obj, dict):
                    account_label = detail_obj.get("account_label") or None
            except json.JSONDecodeError:
                account_label = None
        status = e.status
        rep_status = (rep.status if rep else None) or payload.get("status")
        if rep_status and status in ("UNKNOWN", "PENDING", "SUBMITTED", "NEW", "ROUTING"):
            status = str(rep_status)
        order_id = payload.get("order_id") or _parse_order_id_from_detail(e.detail)
        if _execution_sync_timed_out(e, status, order_id):
            status = "EXPIRED"
        out.append({
            "source_id": e.source_id,
            "signal_id": e.signal_id,
            "broker": e.broker,
            "account_id": e.account_id,
            "account_label": account_label,
            "status": status,
            "detail": e.detail,
            "signal": e.signal,
            "fill_price": payload.get("fill_price"),
            "filled_qty": payload.get("filled_qty"),
            "realized_pnl": payload.get("realized_pnl"),
            "order_id": order_id or payload.get("order_id"),
            "attempt": payload.get("attempt") or _parse_attempt_from_detail(e.detail),
            "created_at": format_et(e.created_at),
        })
    return {"items": out, "total": total, "limit": limit, "offset": offset}


async def _resolve_execution_account_label(
    db: AsyncSession,
    user_id: uuid.UUID,
    record: ExecutionRecord,
    hint_label: Optional[str] = None,
) -> str:
    from app.models import BrokerCredential, UserRouteRule

    label = (hint_label or record.account_label or "").strip()
    if not label and record.detail:
        try:
            detail_obj = json.loads(record.detail)
            if isinstance(detail_obj, dict):
                label = str(detail_obj.get("account_label") or "").strip()
        except json.JSONDecodeError:
            label = ""
    if not label:
        rule = (await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.user_id == user_id,
                UserRouteRule.source_id == record.source_id,
            )
        )).scalars().first()
        if rule and rule.account_label:
            label = rule.account_label.strip()
    if label:
        return label

    cred_q = select(BrokerCredential).where(
        BrokerCredential.user_id == user_id,
        BrokerCredential.broker == record.broker,
    )
    if record.account_id:
        cred_q = cred_q.where(BrokerCredential.account_id == record.account_id)
    creds = (await db.execute(cred_q)).scalars().all()
    if len(creds) == 1 and creds[0].label:
        return creds[0].label
    if len(creds) > 1:
        labels = [c.label for c in creds if c.label]
        raise HTTPException(
            status_code=409,
            detail={
                "error": "ambiguous_broker_account",
                "message": "多个券商账号共用同一 account_id，请在流水线执行步骤选择具体标识名后重新保存",
                "labels": labels,
            },
        )
    raise HTTPException(status_code=404, detail="credentials not found")


async def _dispatch_confirmed_trade(
    db: AsyncSession,
    user_id: uuid.UUID,
    record: ExecutionRecord,
    policy: str,
    account_label_hint: Optional[str] = None,
) -> None:
    from sigtrades_core.brokers import deployment_for

    headers = {"X-Internal-Secret": settings.INTERNAL_SECRET}
    deployment = deployment_for(record.broker)
    account_label = await _resolve_execution_account_label(db, user_id, record, account_label_hint)
    signal_payload = dict(record.signal or {})
    signal_payload["signal_id"] = record.signal_id

    if deployment == "cloud":
        payload = {
            "user_id": str(user_id),
            "signal_id": record.signal_id,
            "source_id": record.source_id,
            "broker": record.broker,
            "account_id": record.account_id,
            "account_label": account_label,
            "order_type_policy": policy,
            "signal": signal_payload,
        }
        async with httpx.AsyncClient(trust_env=False, timeout=10.0) as client:
            resp = await client.post(
                f"{settings.CLOUD_EXECUTOR_URL}/internal/execute",
                json=payload,
                headers=headers,
            )
        resp.raise_for_status()
        return

    execute = {
        "type": "execute_signal",
        "signal_id": record.signal_id,
        "source_id": record.source_id,
        "broker": record.broker,
        "account_id": record.account_id,
        "account_label": account_label,
        "order_type_policy": policy,
        "signal": signal_payload,
    }
    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.post(
            f"{settings.RELAY_GATEWAY_URL}/internal/dispatch",
            json={"user_id": str(user_id), "execute": execute},
            headers=headers,
        )
    resp.raise_for_status()


@router.post("/executions/{signal_id}/confirm")
async def confirm_execution(
    signal_id: str,
    req: ExecutionActionRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExecutionRecord)
        .where(
            ExecutionRecord.user_id == user.id,
            ExecutionRecord.signal_id == signal_id,
            ExecutionRecord.source_id == req.source_id,
            ExecutionRecord.status == "PENDING_CONFIRM",
        )
        .order_by(ExecutionRecord.created_at.desc())
    )
    pending = list(result.scalars().all())
    record = None
    if req.account_label:
        wanted = req.account_label.strip()
        for row in pending:
            row_label = (row.account_label or "").strip()
            if not row_label and row.detail:
                try:
                    detail_obj = json.loads(row.detail)
                    if isinstance(detail_obj, dict):
                        row_label = str(detail_obj.get("account_label") or "").strip()
                except json.JSONDecodeError:
                    row_label = ""
            if row_label == wanted:
                record = row
                break
    elif len(pending) == 1:
        record = pending[0]
    elif pending:
        record = pending[0]
    if record is None:
        raise HTTPException(status_code=404, detail="pending confirmation not found")

    detail: Dict[str, Any] = {}
    try:
        detail = json.loads(record.detail or "{}")
    except json.JSONDecodeError:
        detail = {}

    expires_at = detail.get("expires_at")
    if expires_at:
        exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        if datetime.now(timezone.utc) > exp:
            record.status = "EXPIRED"
            record.detail = "confirmation expired"
            await db.commit()
            raise HTTPException(status_code=400, detail="confirmation expired")

    policy = str(detail.get("order_type_policy") or "MKT_only")
    if req.account_label and not record.account_label:
        record.account_label = req.account_label.strip()
    elif detail.get("account_label") and not record.account_label:
        record.account_label = str(detail["account_label"]).strip()
    record.status = "ROUTING"
    record.detail = "dispatching"
    await db.commit()

    try:
        await _dispatch_confirmed_trade(db, user.id, record, policy, req.account_label)
    except HTTPException:
        record.status = "FAILED"
        await db.commit()
        raise
    except Exception as e:  # noqa: BLE001
        record.status = "FAILED"
        record.detail = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail="dispatch failed") from e

    return {"ok": True, "status": record.status}


@router.post("/executions/{signal_id}/reject")
async def reject_execution(
    signal_id: str,
    req: ExecutionActionRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ExecutionRecord)
        .where(
            ExecutionRecord.user_id == user.id,
            ExecutionRecord.signal_id == signal_id,
            ExecutionRecord.source_id == req.source_id,
            ExecutionRecord.status == "PENDING_CONFIRM",
        )
        .order_by(ExecutionRecord.created_at.desc())
    )
    pending = list(result.scalars().all())
    record = None
    if req.account_label:
        wanted = req.account_label.strip()
        for row in pending:
            row_label = (row.account_label or "").strip()
            if not row_label and row.detail:
                try:
                    detail_obj = json.loads(row.detail)
                    if isinstance(detail_obj, dict):
                        row_label = str(detail_obj.get("account_label") or "").strip()
                except json.JSONDecodeError:
                    row_label = ""
            if row_label == wanted:
                record = row
                break
    elif len(pending) == 1:
        record = pending[0]
    elif pending:
        record = pending[0]
    if record is None:
        raise HTTPException(status_code=404, detail="pending confirmation not found")
    record.status = "REJECTED"
    record.detail = "user rejected"
    await db.commit()
    return {"ok": True, "status": record.status}


_MANUAL_RETRY_STATUSES = frozenset({
    "FAILED",
    "REJECTED",
    "CANCELLED",
    "EXPIRED",
    "DISCARDED_AGENT_OFFLINE",
    "PROTECTIVE_FAILED",
})


@router.post("/executions/{signal_id}/retry")
async def retry_execution(
    signal_id: str,
    req: ExecutionActionRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """失败后手动重新尝试：按当前流水线绑定刷新账号并再次下发。"""
    from app.models import UserBrokerBinding, UserRouteRule
    from app.services.routing import select_bindings_for_rule

    result = await db.execute(
        select(ExecutionRecord)
        .where(
            ExecutionRecord.user_id == user.id,
            ExecutionRecord.signal_id == signal_id,
            ExecutionRecord.source_id == req.source_id,
        )
        .order_by(ExecutionRecord.created_at.desc())
    )
    rows = list(result.scalars().all())
    record = None
    if req.account_label:
        wanted = req.account_label.strip()
        for row in rows:
            if (row.account_label or "").strip() == wanted:
                record = row
                break
    if record is None and rows:
        record = rows[0]
    if record is None:
        raise HTTPException(status_code=404, detail="execution not found")

    status = (record.status or "").upper()
    if status not in _MANUAL_RETRY_STATUSES:
        raise HTTPException(status_code=400, detail="only failed executions can be retried")
    if status == "REJECTED" and "user rejected" in (record.detail or "").lower():
        raise HTTPException(status_code=400, detail="user-rejected executions cannot be retried")
    if not isinstance(record.signal, dict) or not record.signal:
        raise HTTPException(status_code=400, detail="execution has no signal payload")

    rule = (
        await db.execute(
            select(UserRouteRule).where(
                UserRouteRule.user_id == user.id,
                UserRouteRule.source_id == record.source_id,
                UserRouteRule.is_active.is_(True),
            )
        )
    ).scalars().first()
    bindings = list(
        (
            await db.execute(
                select(UserBrokerBinding).where(
                    UserBrokerBinding.user_id == user.id,
                    UserBrokerBinding.enabled.is_(True),
                )
            )
        ).scalars().all()
    )
    if rule and rule.broker:
        routed, blocked = select_bindings_for_rule(bindings, rule)
        if blocked or not routed:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": blocked or "broker_binding_mismatch",
                    "message": "当前流水线券商账户不可用，请先在「券商」核对绑定后再重试",
                },
            )
        binding = routed[0]
        record.broker = binding.broker
        record.account_id = binding.account_id or None
        record.account_label = binding.label or None
        policy = (rule.order_type_policy or binding.order_type_policy or "LMT_then_MKT").strip()
    else:
        if not record.broker or record.broker == "-":
            raise HTTPException(status_code=400, detail="missing broker on execution")
        policy = "LMT_then_MKT"
        if rule and rule.order_type_policy:
            policy = rule.order_type_policy

    if req.account_label and not record.account_label:
        record.account_label = req.account_label.strip()

    record.status = "ROUTING"
    record.detail = "manual_retry"
    await db.commit()

    try:
        await _dispatch_confirmed_trade(db, user.id, record, policy, record.account_label)
    except HTTPException:
        record.status = "FAILED"
        await db.commit()
        raise
    except Exception as e:  # noqa: BLE001
        record.status = "FAILED"
        record.detail = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail="dispatch failed") from e

    return {"ok": True, "status": record.status, "broker": record.broker}


@router.get("/agent-status")
async def agent_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentPresenceRow).where(AgentPresenceRow.user_id == user.id))
    row = result.scalar_one_or_none()
    if not row:
        return {"online": False, "brokers": {}}
    return {"online": row.online, "brokers": row.brokers}


@router.post("/kill-switch")
async def kill_switch(
    req: KillSwitchRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    import httpx
    from app.config import settings as cfg

    user.kill_switch = req.enabled
    await db.commit()
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=5.0) as client:
            await client.post(
                f"{cfg.RELAY_GATEWAY_URL}/internal/pause",
                json={
                    "user_id": str(user.id),
                    "paused": req.enabled,
                    "reason": "kill_switch",
                },
                headers={"X-Internal-Secret": cfg.INTERNAL_SECRET},
            )
    except Exception:  # noqa: BLE001
        pass
    return {"kill_switch": user.kill_switch}


@router.get("/entitlements")
async def entitlements(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    plan = await get_active_plan(db, user.id)
    return {
        "plan_code": plan.code if plan else None,
        "features": plan_features(plan),
    }


class RedeemPromotionRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=64)


@router.post("/promotions/redeem")
async def redeem_promotion(
    req: RedeemPromotionRequest,
    user: User = Depends(get_verified_user),
    db: AsyncSession = Depends(get_db),
):
    """用户兑换活动码 / 合作一次性码。"""
    from app.services.promotion_redeem import redeem_code_for_user

    data = await redeem_code_for_user(db, user, req.code)
    return {"success": True, "data": data}
