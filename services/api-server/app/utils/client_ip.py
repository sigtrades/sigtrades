"""从 FastAPI Request 解析真实客户端 IP（代理 / CDN）。"""

from __future__ import annotations

import ipaddress
from typing import Optional

from fastapi import Request


def is_private_or_loopback_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address((ip or "").strip())
        return bool(addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)
    except ValueError:
        return True


def _clean_ip(value: str | None) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    if s.startswith("[") and "]" in s:
        s = s[1 : s.index("]")]
    elif s.count(":") == 1 and "." in s:
        s = s.split(":", 1)[0]
    try:
        ipaddress.ip_address(s)
        return s
    except ValueError:
        return ""


def _first_public_ip(values: list[str]) -> str:
    fallback = ""
    for raw in values:
        ip = _clean_ip(raw)
        if not ip:
            continue
        if not fallback:
            fallback = ip
        if not is_private_or_loopback_ip(ip):
            return ip
    return fallback


def get_client_ip(request: Request) -> str:
    h = request.headers
    for key in ("cf-connecting-ip", "true-client-ip"):
        v = h.get(key)
        if v:
            ip = _clean_ip(v.split(",")[0])
            if ip:
                return ip

    xff = h.get("x-forwarded-for")
    if xff:
        ip = _first_public_ip([p.strip() for p in xff.split(",") if p.strip()])
        if ip:
            return ip

    for key in ("x-real-ip", "x-client-ip"):
        v = h.get(key)
        if v:
            ip = _clean_ip(v.split(",")[0])
            if ip:
                return ip

    try:
        c = request.client
        if c and c.host:
            return _clean_ip(c.host) or c.host
    except Exception:  # noqa: BLE001
        pass
    return ""


def get_cf_ip_country(request: Request) -> Optional[str]:
    v = (request.headers.get("cf-ipcountry") or request.headers.get("CF-IPCountry") or "").strip()
    if len(v) == 2 and v.isalpha():
        return v.upper()
    if v in ("XX", "T1"):
        return None
    return None
