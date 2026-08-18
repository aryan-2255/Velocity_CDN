import logging
from pathlib import Path

import geoip2.database
import geoip2.errors
from fastapi import Request

from app.config import settings, trusted_proxy_list

logger = logging.getLogger("geoip")

_reader: geoip2.database.Reader | None = None
_load_attempted = False


def _get_reader() -> geoip2.database.Reader | None:
    global _reader, _load_attempted
    if _load_attempted:
        return _reader
    _load_attempted = True
    path = Path(settings.geoip_db_path)
    if not path.exists():
        logger.warning("GeoLite2 DB not found at %s — geo resolution disabled, use ?region= override", path)
        return None
    _reader = geoip2.database.Reader(str(path))
    return _reader


def geoip_available() -> bool:
    """Whether real geo resolution can happen at all — false when no GeoLite2 DB
    is provisioned, in which case every 'auto' request falls back to DEFAULT_COORDS."""
    return _get_reader() is not None


def resolve_ip(ip: str) -> tuple[float, float, str] | None:
    """Returns (lat, lon, human-readable label) or None if unresolvable —
    missing DB, private/reserved IP (common in local dev), or a lookup miss."""
    reader = _get_reader()
    if reader is None:
        return None
    try:
        response = reader.city(ip)
    except (geoip2.errors.AddressNotFoundError, ValueError):
        return None
    if response.location.latitude is None or response.location.longitude is None:
        return None
    city = response.city.name
    country = response.country.iso_code
    label = ", ".join(p for p in (city, country) if p) or ip
    return response.location.latitude, response.location.longitude, label


def get_client_ip(request: Request) -> str:
    """Real client IP. X-Forwarded-For is only trusted when the immediate peer
    is a known proxy (TRUSTED_PROXIES) — otherwise it's client-spoofable and
    would let anyone fake their geo-routing."""
    peer_ip = request.client.host if request.client else ""
    trusted = trusted_proxy_list()
    if trusted and peer_ip in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return peer_ip
