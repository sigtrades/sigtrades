"""Discord 用户 Token REST 调用（配置向导：验证账号、拉服务器/频道列表）。"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

import httpx

DISCORD_API = "https://discord.com/api/v9"
TEXT_CHANNEL_TYPES = {0, 5, 10, 11, 12}


def _headers(token: str) -> dict[str, str]:
    # 与 ingest discord_identity 保持一致的浏览器指纹
    import base64
    import json

    props = {
        "os": "Mac OS X",
        "browser": "Chrome",
        "device": "",
        "system_locale": "zh-CN",
        "browser_user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "browser_version": "131.0.0.0",
        "os_version": "10.15.7",
        "referrer": "",
        "referring_domain": "",
        "release_channel": "stable",
        "client_build_number": 300000,
        "client_event_source": None,
    }
    super_props = base64.b64encode(json.dumps(props, separators=(",", ":")).encode()).decode()
    return {
        "Authorization": token.strip(),
        "User-Agent": props["browser_user_agent"],
        "X-Super-Properties": super_props,
        "X-Discord-Locale": "zh-CN",
        "X-Discord-Timezone": "Asia/Shanghai",
        "Content-Type": "application/json",
    }


async def validate_user_token(token: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=12.0) as client:
        resp = await client.get(f"{DISCORD_API}/users/@me", headers=_headers(token))
    if resp.status_code == 401:
        raise ValueError("invalid or expired discord token")
    resp.raise_for_status()
    data = resp.json()
    return {
        "id": data.get("id"),
        "username": data.get("username"),
        "global_name": data.get("global_name"),
    }


def guild_icon_cdn_urls(guild_id: str, icon: str, size: int = 64) -> List[str]:
    ext = "gif" if icon.startswith("a_") else "png"
    urls = [
        f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.{ext}?size={size}",
        f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.webp?size={size}",
    ]
    if ext != "png":
        urls.append(f"https://cdn.discordapp.com/icons/{guild_id}/{icon}.png?size={size}")
    return urls


async def _fetch_guild_detail_icon(token: str, guild_id: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{DISCORD_API}/guilds/{guild_id}", headers=_headers(token))
    if resp.status_code != 200:
        return None
    icon = resp.json().get("icon")
    return icon if icon else None


async def fetch_guilds(token: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{DISCORD_API}/users/@me/guilds", headers=_headers(token))
    resp.raise_for_status()
    guilds = [{"id": g["id"], "name": g.get("name", ""), "icon": g.get("icon")} for g in resp.json()]

    missing = [g for g in guilds if not g.get("icon")]
    if missing:
        icons = await asyncio.gather(*[_fetch_guild_detail_icon(token, g["id"]) for g in missing])
        for guild, icon in zip(missing, icons):
            if icon:
                guild["icon"] = icon
    return guilds


async def fetch_guild_channels(token: str, guild_id: str) -> List[Dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{DISCORD_API}/guilds/{guild_id}/channels", headers=_headers(token))
    if resp.status_code == 403:
        raise ValueError("no access to this server")
    resp.raise_for_status()
    out = []
    for ch in resp.json():
        if ch.get("type") not in TEXT_CHANNEL_TYPES:
            continue
        out.append({"id": ch["id"], "name": ch.get("name", ""), "guild_id": guild_id, "type": ch.get("type")})
    return sorted(out, key=lambda x: x["name"].lower())
