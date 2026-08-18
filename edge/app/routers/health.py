from fastapi import APIRouter, Request

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict:
    cache_manager = request.app.state.cache_manager
    return {
        "status": "healthy",
        "edge": settings.edge_name,
        "region": settings.region,
        "cache_policy": settings.cache_policy,
        "occupancy_bytes": cache_manager.occupancy_bytes,
        "occupancy_pct": round(cache_manager.occupancy_pct, 4),
        "entry_count": cache_manager.entry_count,
        "hit_ratio": round(cache_manager.hit_ratio, 4),
        "hits": cache_manager.hits,
        "misses": cache_manager.misses,
        "stale_serves": cache_manager.stale_serves,
        "errors": cache_manager.errors,
    }
