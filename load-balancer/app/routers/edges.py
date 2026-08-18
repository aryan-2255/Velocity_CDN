import httpx
from fastapi import APIRouter, Request

from app.config import LOCAL_EDGE_RADIUS_KM, REGION_COORDS, REGION_LABELS, settings
from app.geoip import geoip_available
from app.routing import haversine_km, rank_edges

router = APIRouter(tags=["edges"])


@router.get("/edges")
async def list_edges(request: Request) -> list[dict]:
    registry = request.app.state.registry
    return [
        {
            "id": e.id,
            "name": e.name,
            "region": e.region,
            "base_url": e.base_url,
            "lat": e.lat,
            "lon": e.lon,
            "status": e.status,
            "cache_policy": e.cache_policy,
            "live": e.live,
        }
        for e in registry.all()
    ]


@router.get("/origin")
async def origin_status(request: Request) -> dict:
    """Origin's health as the dashboard sees it. Unreachable is a status, not an
    error — an Origin that's down still lets edges serve hits (and stale copies),
    which is exactly the resilience worth showing."""
    http_client: httpx.AsyncClient = request.app.state.http_client
    try:
        resp = await http_client.get(f"{settings.origin_base_url}/health", timeout=5.0)
        resp.raise_for_status()
        return {"reachable": True, **resp.json()}
    except httpx.HTTPError as exc:
        return {"reachable": False, "status": "unreachable", "error": str(exc)}


@router.get("/regions")
async def list_regions(request: Request) -> dict:
    """Manual-override choices, each resolved through the *same* rank_edges()
    the real /fetch path uses — so what the dropdown promises is what routing
    actually does, including when an edge is unhealthy and drops out."""
    registry = request.app.state.registry
    edges = registry.all()

    out = []
    for value, (lat, lon) in REGION_COORDS.items():
        ranked = rank_edges(lat, lon, edges)
        nearest = ranked[0] if ranked else None
        distance_km = haversine_km(lat, lon, nearest.lat, nearest.lon) if nearest else None
        out.append({
            "value": value,
            "label": REGION_LABELS.get(value, value),
            "lat": lat,
            "lon": lon,
            "nearest_edge": nearest.name if nearest else None,
            "distance_km": round(distance_km) if distance_km is not None else None,
            # "local" means an edge sits in this city, so the choice doesn't
            # exercise cross-region routing — the dashboard groups on this.
            "has_local_edge": distance_km is not None and distance_km <= LOCAL_EDGE_RADIUS_KM,
        })
    return {"geoip_enabled": geoip_available(), "regions": out}
