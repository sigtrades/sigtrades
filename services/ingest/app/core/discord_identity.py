"""Discord 网页客户端身份仿真（用户 Token Gateway / REST）。"""

from __future__ import annotations

import base64
import json
import platform
import sys

DISCORD_API_BASE = "https://discord.com/api/v9"
GATEWAY_URL = "wss://gateway.discord.gg/?v=10&encoding=json"
_CLIENT_BUILD_NUMBER = 300000
_BROWSER_VERSION = "131.0.0.0"


def _os_label() -> str:
    if sys.platform == "darwin":
        return "Mac OS X"
    if sys.platform.startswith("win"):
        return "Windows"
    return "Linux"


def _os_version() -> str:
    if sys.platform == "darwin":
        return platform.mac_ver()[0] or "10.15.7"
    if sys.platform.startswith("win"):
        return platform.release() or "10"
    return platform.release() or "5.0"


def _gateway_os() -> str:
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


def _ua_platform() -> str:
    if sys.platform == "darwin":
        return f"Macintosh; Intel Mac OS X {_os_version().replace('.', '_')}"
    if sys.platform.startswith("win"):
        return f"Windows NT {platform.release() or '10.0'}; Win64; x64"
    return "X11; Linux x86_64"


def user_agent() -> str:
    return (
        f"Mozilla/5.0 ({_ua_platform()}) AppleWebKit/537.36 "
        f"(KHTML, like Gecko) Chrome/{_BROWSER_VERSION} Safari/537.36"
    )


def build_super_properties() -> str:
    props = {
        "os": _os_label(),
        "browser": "Chrome",
        "device": "",
        "system_locale": "zh-CN",
        "browser_user_agent": user_agent(),
        "browser_version": _BROWSER_VERSION,
        "os_version": _os_version(),
        "referrer": "",
        "referring_domain": "",
        "referrer_current": "",
        "referring_domain_current": "",
        "release_channel": "stable",
        "client_build_number": _CLIENT_BUILD_NUMBER,
        "client_event_source": None,
    }
    return base64.b64encode(json.dumps(props, separators=(",", ":")).encode()).decode("ascii")


def api_headers(token: str, *, locale: str = "zh-CN", timezone: str = "Asia/Shanghai") -> dict[str, str]:
    return {
        "Authorization": token,
        "User-Agent": user_agent(),
        "X-Super-Properties": build_super_properties(),
        "X-Discord-Locale": locale,
        "X-Discord-Timezone": timezone,
        "Content-Type": "application/json",
    }


def gateway_identify_payload(token: str) -> dict:
    return {
        "op": 2,
        "d": {
            "token": token,
            "capabilities": 125,
            "properties": {
                "$os": _gateway_os(),
                "$browser": "Chrome",
                "$device": "",
                "$referrer": "",
                "$referring_domain": "",
            },
            "presence": {
                "status": "online",
                "since": 0,
                "activities": [],
                "afk": False,
            },
            "compress": False,
            "client_state": {
                "guild_hashes": {},
                "highest_last_message_id": "0",
                "read_state_version": 0,
                "user_guild_settings_version": 0,
                "user_settings_version": 0,
                "private_channels_version": 0,
            },
        },
    }
