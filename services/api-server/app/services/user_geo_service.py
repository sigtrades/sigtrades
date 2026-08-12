"""用户 IP / 国家事件：注册、登录。"""

from __future__ import annotations

import logging
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional

from fastapi import Request
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserGeoEvent
from app.services.geoip_service import country_and_city_from_ip
from app.utils.client_ip import get_cf_ip_country, get_client_ip

logger = logging.getLogger(__name__)


async def record_user_geo_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    request: Request,
    *,
    event_type: str,
    auth_method: Optional[str] = None,
) -> None:
    try:
        ip = get_client_ip(request) or ""
        country = get_cf_ip_country(request)
        region_name: Optional[str] = None
        mmdb_country, mmdb_region = country_and_city_from_ip(ip) if ip else (None, None)
        if not country and mmdb_country:
            country = mmdb_country
        if mmdb_region:
            region_name = mmdb_region[:200]

        db.add(UserGeoEvent(
            user_id=user_id,
            ip_address=ip[:45],
            country_code=country,
            city_name=region_name,
            event_type=event_type,
            auth_method=auth_method,
        ))
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.warning("record_user_geo_event failed user=%s type=%s: %s", user_id, event_type, e)
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def fetch_registration_by_users(
    db: AsyncSession, user_ids: List[uuid.UUID]
) -> Dict[uuid.UUID, UserGeoEvent]:
    if not user_ids:
        return {}
    q = (
        select(UserGeoEvent)
        .where(UserGeoEvent.user_id.in_(user_ids), UserGeoEvent.event_type == "registration")
        .order_by(UserGeoEvent.user_id, UserGeoEvent.created_at.asc())
    )
    rows = (await db.execute(q)).scalars().all()
    out: Dict[uuid.UUID, UserGeoEvent] = {}
    for r in rows:
        if r.user_id not in out:
            out[r.user_id] = r
    return out


async def fetch_latest_login_by_users(
    db: AsyncSession, user_ids: List[uuid.UUID]
) -> Dict[uuid.UUID, UserGeoEvent]:
    if not user_ids:
        return {}
    q = (
        select(UserGeoEvent)
        .where(UserGeoEvent.user_id.in_(user_ids), UserGeoEvent.event_type == "login")
        .order_by(UserGeoEvent.user_id, UserGeoEvent.created_at.desc())
    )
    rows = (await db.execute(q)).scalars().all()
    out: Dict[uuid.UUID, UserGeoEvent] = {}
    for r in rows:
        if r.user_id not in out:
            out[r.user_id] = r
    return out


def _geo_snapshot(ev: Optional[UserGeoEvent]) -> Optional[Dict[str, Any]]:
    if not ev:
        return None
    country = ev.country_code
    city = ev.city_name
    ip = ev.ip_address or ""
    # 展示兜底：历史记录在装 mmdb 前只有 IP、无国家码时即时解析（不写库）
    if ip and not country:
        mmdb_country, mmdb_region = country_and_city_from_ip(ip)
        if mmdb_country:
            country = mmdb_country
        if not city and mmdb_region:
            city = mmdb_region
    return {
        "ip": ip,
        "country_code": country,
        "city_name": city,
    }


async def count_users_without_registration_event(db: AsyncSession) -> int:
    has_reg = exists(
        select(1)
        .select_from(UserGeoEvent)
        .where(UserGeoEvent.user_id == User.id, UserGeoEvent.event_type == "registration")
    )
    q = select(func.count()).select_from(User).where(~has_reg)
    return int((await db.execute(q)).scalar() or 0)


async def country_distribution_by_registration_or_latest_login(
    db: AsyncSession,
) -> Dict[str, Any]:
    user_ids = list((await db.execute(select(User.id))).scalars().all())
    if not user_ids:
        return {
            "by_country": [],
            "users_without_geo": 0,
            "users_fallback_to_last_login": 0,
        }

    reg_map = await fetch_registration_by_users(db, user_ids)
    login_map = await fetch_latest_login_by_users(db, user_ids)

    counts: Counter[Optional[str]] = Counter()
    users_without_geo = 0
    users_fallback_to_last_login = 0

    for user_id in user_ids:
        reg = reg_map.get(user_id)
        login = login_map.get(user_id)
        reg_country = (reg.country_code or "").upper() if reg and reg.country_code else None
        login_country = (login.country_code or "").upper() if login and login.country_code else None

        country = reg_country
        if not country and login_country:
            country = login_country
            users_fallback_to_last_login += 1

        if not country:
            users_without_geo += 1
        counts[country] += 1

    rows = [
        {"country_code": country, "count": count}
        for country, count in sorted(
            counts.items(),
            key=lambda item: (item[0] is None, -item[1], item[0] or ""),
        )
    ]
    return {
        "by_country": rows,
        "users_without_geo": users_without_geo,
        "users_fallback_to_last_login": users_fallback_to_last_login,
    }


def geo_snapshot(ev: Optional[UserGeoEvent]) -> Optional[Dict[str, Any]]:
    return _geo_snapshot(ev)
