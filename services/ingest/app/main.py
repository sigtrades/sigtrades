"""ingest：插件式信号连接器宿主（Webhook + Discord Gateway）。"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Set

import httpx
from fastapi import FastAPI, Header, HTTPException, Request

from app.config import settings
from app.connectors.discord import (
    DiscordConnector,
    normalized_to_inbound,
    verify_discord_signature,
)
from app.connectors.webhook import parse_webhook_payload, verify_hmac
from app.core.discord_bot import start_discord_bot, stop_discord_bot
from app.core.discord_user_bot import (
    get_preview_messages,
    get_test_messages,
    start_discord_user_bot,
    start_test_listen,
    stop_discord_user_bot,
    stop_test_listen,
)
from app.core.telegram_bot import get_telegram_bot, process_telegram_update, start_telegram_bot, stop_telegram_bot
from app.core.forward import forward_inbound

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ingest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await start_discord_bot()
    await start_discord_user_bot()
    await start_telegram_bot()
    logger.info("ingest ready (discord_manager=on user_bridge=on telegram=%s)", bool(settings.TELEGRAM_BOT_TOKEN))
    yield
    await stop_telegram_bot()
    await stop_discord_user_bot()
    await stop_discord_bot()


app = FastAPI(title="sigtrades ingest", lifespan=lifespan)

# 防止 create_task 被 GC 提前回收
_bg_tasks: Set[asyncio.Task] = set()


def _forward_in_background(inbound: Dict[str, Any]) -> None:
    """Webhook 快速 ACK：路由/执行转后台，避免上游按超时误判失败而重投。"""

    async def _run() -> None:
        try:
            await forward_inbound(inbound)
        except Exception:  # noqa: BLE001
            logger.exception("后台转发失败 signal_id=%s", inbound.get("signal_id"))

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)


async def _resolve_webhook_token(token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
        resp = await client.post(
            f"{settings.API_SERVER_URL}/internal/resolve-webhook-token",
            json={"token": token},
            headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
        )
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="invalid webhook token")
    resp.raise_for_status()
    return resp.json()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "ingest",
        "discord_manager": True,
        "discord_user_bridge": True,
        "telegram_bot": bool(settings.TELEGRAM_BOT_TOKEN),
    }


def _check_internal(secret: Optional[str]) -> None:
    if secret != settings.INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.post("/internal/discord-user/test-listen")
async def internal_discord_user_test_listen(
    request: Request,
    x_internal_secret: Optional[str] = Header(default=None, alias="X-Internal-Secret"),
):
    _check_internal(x_internal_secret)
    body = await request.json()
    session_id = await start_test_listen(
        body.get("user_token", ""),
        body.get("channel_ids") or [],
        body.get("channel_labels") or {},
    )
    return {"session_id": session_id}


@app.get("/internal/discord-user/test-messages")
async def internal_discord_user_test_messages(
    session_id: str,
    x_internal_secret: Optional[str] = Header(default=None, alias="X-Internal-Secret"),
):
    _check_internal(x_internal_secret)
    return {"messages": get_test_messages(session_id)}


@app.post("/internal/discord-user/test-stop")
async def internal_discord_user_test_stop(
    request: Request,
    x_internal_secret: Optional[str] = Header(default=None, alias="X-Internal-Secret"),
):
    _check_internal(x_internal_secret)
    body = await request.json()
    await stop_test_listen(body.get("session_id", ""))
    return {"ok": True}


@app.get("/internal/discord-user/preview/{source_id}")
async def internal_discord_user_preview(
    source_id: str,
    x_internal_secret: Optional[str] = Header(default=None, alias="X-Internal-Secret"),
):
    _check_internal(x_internal_secret)
    return {"messages": get_preview_messages(source_id)}


@app.post("/ingest/wh/{token}")
async def webhook_ingest(
    token: str,
    request: Request,
    x_signature: Optional[str] = Header(default=None, alias="X-Signature"),
):
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {"raw_text": body.decode("utf-8", errors="replace")}

    meta = await _resolve_webhook_token(token)
    if not verify_hmac(
        body, x_signature, meta.get("hmac_secret"),
        require_secret=settings.is_production,
    ):
        raise HTTPException(status_code=401, detail="invalid HMAC signature")

    _signal_id, inbound = parse_webhook_payload(
        payload,
        source_id=meta["source_id"],
        owner_user_id=meta["owner_user_id"],
    )
    # 立即 ACK：解析/路由/下发全部后台执行。上游（TradingView / SunnyQuant 等）
    # 超时通常只有几秒，同步等路由完成会被误判失败并触发重投。
    _forward_in_background(inbound)
    return {"accepted": True, "signal_id": inbound["signal_id"]}


@app.post("/ingest/discord/events")
async def discord_events(
    request: Request,
    x_signature_ed25519: Optional[str] = Header(default=None, alias="X-Signature-Ed25519"),
    x_signature_timestamp: Optional[str] = Header(default=None, alias="X-Signature-Timestamp"),
):
    body = await request.body()
    if not verify_discord_signature(
        body, x_signature_ed25519 or "", x_signature_timestamp or "", settings.DISCORD_PUBLIC_KEY
    ):
        raise HTTPException(status_code=401, detail="invalid discord signature")

    event = json.loads(body)

    if event.get("type") == 1:
        return {"type": 1}

    source_id = event.get("source_id") or "discord-default"
    owner = event.get("owner_user_id")
    config = {"ownership": event.get("ownership", "user_private"), "owner_user_id": owner}

    connector = DiscordConnector(source_id=source_id, config=config, on_signal=lambda _: None)
    normalized_list = connector.parse(event.get("d", event))

    results = []
    for ns in normalized_list:
        inbound = normalized_to_inbound(ns)
        result = await forward_inbound(inbound)
        results.append({"signal_id": inbound["signal_id"], "routed": result})

    return {"accepted": True, "count": len(results), "results": results}


@app.post("/ingest/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Optional[str] = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    """Telegram Bot webhook（生产环境可替代 long-polling）。"""
    if settings.TELEGRAM_WEBHOOK_SECRET and x_telegram_bot_api_secret_token != settings.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="invalid telegram webhook secret")
    try:
        update = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="invalid json") from exc

    bot = get_telegram_bot()
    chat_map: Dict[str, Any] = {}
    if bot:
        await bot.ensure_sources()
        chat_map = bot._chat_map  # noqa: SLF001
    else:
        # webhook-only 模式：临时拉取源配置
        async with httpx.AsyncClient(trust_env=False, timeout=8.0) as client:
            resp = await client.get(
                f"{settings.API_SERVER_URL}/internal/telegram-sources",
                headers={"X-Internal-Secret": settings.INTERNAL_SECRET},
            )
        resp.raise_for_status()
        for src in resp.json().get("sources", []):
            for ch in src.get("chat_ids") or []:
                chat_map[str(ch)] = src

    count = await process_telegram_update(update, chat_map)
    return {"ok": True, "forwarded": count}
