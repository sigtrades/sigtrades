"""公网 IP → 国家/省份（GeoLite2 mmdb，可选）。"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional, Tuple

from app.config import settings
from app.utils.client_ip import is_private_or_loopback_ip

logger = logging.getLogger(__name__)

_country_reader = None
_country_path: Optional[str] = None
_city_reader = None
_city_path: Optional[str] = None
_lock = threading.Lock()


def _get_country_reader():
    global _country_reader, _country_path
    path = (settings.GEOIP2_COUNTRY_DB_PATH or "").strip()
    if not path or not os.path.isfile(path):
        return None
    with _lock:
        if _country_reader is not None and _country_path == path:
            return _country_reader
        try:
            import geoip2.database

            r = geoip2.database.Reader(path)
            _country_reader = r
            _country_path = path
            return r
        except Exception as e:  # noqa: BLE001
            logger.warning("GeoIP2 Country Reader init failed path=%s: %s", path, e)
            return None


def _get_city_reader():
    global _city_reader, _city_path
    path = (settings.GEOIP2_CITY_DB_PATH or "").strip()
    if not path or not os.path.isfile(path):
        return None
    with _lock:
        if _city_reader is not None and _city_path == path:
            return _city_reader
        try:
            import geoip2.database

            r = geoip2.database.Reader(path)
            _city_reader = r
            _city_path = path
            return r
        except Exception as e:  # noqa: BLE001
            logger.warning("GeoIP2 City Reader init failed path=%s: %s", path, e)
            return None


def country_and_region_from_ip(ip: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    ip = (ip or "").strip()
    if not ip or is_private_or_loopback_ip(ip):
        return None, None, None

    cr = _get_city_reader()
    if cr:
        try:
            rec = cr.city(ip)
            cc = (rec.country.iso_code or "").strip().upper()
            country = cc if len(cc) == 2 else None
            region = None
            if rec.subdivisions:
                region = (rec.subdivisions[0].name or "").strip() or None
            if not region:
                region = (rec.city.name or "").strip() or None
            city = (rec.city.name or "").strip() or None
            return country, region, city
        except Exception:  # noqa: BLE001
            pass

    co = _get_country_reader()
    if co:
        try:
            rec = co.country(ip)
            cc = (rec.country.iso_code or "").strip().upper()
            if len(cc) == 2:
                return cc, None, None
        except Exception:  # noqa: BLE001
            pass
    return None, None, None


def country_and_city_from_ip(ip: str) -> Tuple[Optional[str], Optional[str]]:
    country, region, _ = country_and_region_from_ip(ip)
    return country, region
