from fastapi import APIRouter, Request

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/purge/{key:path}")
async def purge(key: str, request: Request) -> dict:
    cache_manager = request.app.state.cache_manager
    purged = await cache_manager.purge(key)
    return {"key": key, "purged": purged}
