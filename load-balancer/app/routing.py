import math

from app.edge_registry import EdgeInfo


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0  # Earth radius, km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def rank_edges(client_lat: float, client_lon: float, edges: list[EdgeInfo]) -> list[EdgeInfo]:
    """Healthy, enabled edges only, nearest first. Failover just walks this list."""
    candidates = [e for e in edges if e.status == "healthy" and e.lat is not None and e.lon is not None]
    return sorted(candidates, key=lambda e: haversine_km(client_lat, client_lon, e.lat, e.lon))
