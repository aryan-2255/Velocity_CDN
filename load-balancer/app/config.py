from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    origin_base_url: str = "http://origin:8000"

    # Only trust X-Forwarded-For from these hop IPs (e.g. the Nginx box in front of this
    # service in Phase 3). Never trust it blindly, that's a client-spoofable geo bypass.
    trusted_proxies: str = ""  # comma-separated

    # Optional: absent in local dev unless MaxMind license key is provisioned (spec section 16).
    # geoip.py degrades gracefully, falls through to "unresolved" rather than crashing.
    geoip_db_path: str = "/geoip/GeoLite2-City.mmdb"

    health_check_interval_seconds: float = 10.0
    edge_refresh_interval_seconds: float = 15.0
    edge_request_timeout_seconds: float = 5.0
    health_check_timeout_seconds: float = 2.0

    cors_origins: str = "*"  # comma-separated, "*" for local dev

    # Dashboard uploads are proxied through the LB; cap them so an open endpoint
    # can't be used to fill the S3 bucket. 25MB comfortably covers the demo
    # assets (largest is ~1.3MB) without inviting abuse.
    max_upload_bytes: int = 25 * 1024 * 1024
    upload_timeout_seconds: float = 120.0


settings = Settings()


def trusted_proxy_list() -> list[str]:
    return [p.strip() for p in settings.trusted_proxies.split(",") if p.strip()]


def cors_origin_list() -> list[str]:
    return [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


# Demo client locations for the manual override (spec section 5.4). These are
# *client* positions to simulate, "pretend the user is here", not server
# locations. Cities with no nearby edge are the interesting ones: they're what
# actually exercises nearest-edge selection. The dashboard reads this list from
# GET /regions rather than keeping its own copy, so the two can't drift.
REGION_COORDS: dict[str, tuple[float, float]] = {
    # Cities co-located with an edge
    "mumbai": (19.0760, 72.8777),
    "frankfurt": (50.1109, 8.6821),
    "singapore": (1.3521, 103.8198),
    # Asia
    "tokyo": (35.6762, 139.6503),
    "seoul": (37.5665, 126.9780),
    "beijing": (39.9042, 116.4074),
    "hong_kong": (22.3193, 114.1694),
    "jakarta": (-6.2088, 106.8456),
    "bangkok": (13.7563, 100.5018),
    "manila": (14.5995, 120.9842),
    "delhi": (28.6139, 77.2090),
    "bengaluru": (12.9716, 77.5946),
    "dubai": (25.2048, 55.2708),
    # Europe
    "london": (51.5074, -0.1278),
    "paris": (48.8566, 2.3522),
    "madrid": (40.4168, -3.7038),
    "stockholm": (59.3293, 18.0686),
    "moscow": (55.7558, 37.6173),
    "istanbul": (41.0082, 28.9784),
    # Americas
    "new_york": (40.7128, -74.0060),
    "san_francisco": (37.7749, -122.4194),
    "chicago": (41.8781, -87.6298),
    "toronto": (43.6532, -79.3832),
    "mexico_city": (19.4326, -99.1332),
    "sao_paulo": (-23.5505, -46.6333),
    "buenos_aires": (-34.6037, -58.3816),
    # Africa & Oceania
    "lagos": (6.5244, 3.3792),
    "nairobi": (-1.2921, 36.8219),
    "cairo": (30.0444, 31.2357),
    "johannesburg": (-26.2041, 28.0473),
    "cape_town": (-33.9249, 18.4241),
    "sydney": (-33.8688, 151.2093),
    "auckland": (-36.8485, 174.7633),
}

REGION_LABELS: dict[str, str] = {
    "mumbai": "Mumbai",
    "frankfurt": "Frankfurt",
    "singapore": "Singapore",
    "tokyo": "Tokyo",
    "seoul": "Seoul",
    "beijing": "Beijing",
    "hong_kong": "Hong Kong",
    "jakarta": "Jakarta",
    "bangkok": "Bangkok",
    "manila": "Manila",
    "delhi": "Delhi",
    "bengaluru": "Bengaluru",
    "dubai": "Dubai",
    "london": "London",
    "paris": "Paris",
    "madrid": "Madrid",
    "stockholm": "Stockholm",
    "moscow": "Moscow",
    "istanbul": "Istanbul",
    "new_york": "New York",
    "san_francisco": "San Francisco",
    "chicago": "Chicago",
    "toronto": "Toronto",
    "mexico_city": "Mexico City",
    "sao_paulo": "São Paulo",
    "buenos_aires": "Buenos Aires",
    "lagos": "Lagos",
    "nairobi": "Nairobi",
    "cairo": "Cairo",
    "johannesburg": "Johannesburg",
    "cape_town": "Cape Town",
    "sydney": "Sydney",
    "auckland": "Auckland",
}

# A client this close to an edge is treated as "has a local edge" for grouping
# purposes. Generous enough to absorb the gap between a city's coordinates and
# the AWS region's actual datacenter.
LOCAL_EDGE_RADIUS_KM = 500.0

# Where an unresolvable client IP falls back to (no GeoLite2 DB provisioned yet, or a
# private/reserved address like localhost during local dev). Origin's own region,
# since that's the CDN's "home" and a defensible default.
DEFAULT_COORDS: tuple[float, float] = (39.0438, -77.4874)  # us-east-1 (N. Virginia)
