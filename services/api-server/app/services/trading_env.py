"""券商执行环境：模拟盘 / 实盘（与前端 isBrokerPaperMode 口径对齐）。"""

from __future__ import annotations

import re
from typing import Any, Optional

_TIGER_PAPER_ACCOUNT = re.compile(r"^\d{17,}$")
_LIVE_ENV = frozenset({"production", "prod", "live", "online"})
_PAPER_ENV = frozenset({"paper", "test", "sandbox", "uat", "simulate", "simulation"})


def resolve_is_paper(
    broker: Optional[str],
    account_id: Optional[str] = None,
    env: Optional[str] = None,
) -> Optional[bool]:
    """True=模拟, False=实盘, None=无法判断。"""
    key = (broker or "").strip().lower()
    aid = (account_id or "").strip()
    e = (env or "").strip().lower()
    if not key:
        return None

    if key == "ibkr":
        if aid == "tws-paper":
            return True
        if aid == "tws-live":
            return False
        return None

    if key == "ibkr_web":
        if e in _LIVE_ENV:
            return False
        if e in _PAPER_ENV:
            return True
        return None

    if key == "futu":
        if aid in ("futu-simulate", "simulate"):
            return True
        if aid in ("futu-real", "real"):
            return False
        return None

    if key == "tiger":
        if aid:
            if _TIGER_PAPER_ACCOUNT.match(aid):
                return True
            if aid.isdigit():
                return False
        if e in _LIVE_ENV:
            return False
        if e in _PAPER_ENV:
            return True
        return None

    if key == "schwab":
        return False

    if key == "usmart":
        if not e:
            return False
        return e in _PAPER_ENV

    # alpaca / longbridge / others：看凭证 env
    if not e:
        return None
    if e in _LIVE_ENV:
        return False
    if e in _PAPER_ENV:
        return True
    return None


def env_label_zh(is_paper: Optional[bool]) -> str:
    if is_paper is True:
        return "模拟"
    if is_paper is False:
        return "实盘"
    return "—"


def credential_env(config: Any) -> Optional[str]:
    if not isinstance(config, dict):
        return None
    raw = config.get("env")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None
