from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.config import settings
from app.origin_client import OriginNotFoundError, OriginUnreachableError

router = APIRouter(tags=["content"])


@router.get("/content/{key:path}")
async def get_content(key: str, request: Request) -> Response:
    cache_manager = request.app.state.cache_manager

    try:
        result = await cache_manager.get(key)
    except OriginNotFoundError:
        raise HTTPException(status_code=404, detail="file not found") from None
    except OriginUnreachableError:
        return Response(
            content=b"origin unreachable and no cached copy available",
            status_code=502,
            headers={"X-Cache-Result": "error", "X-Served-By": settings.edge_name},
        )

    headers = {"X-Cache-Result": result.source, "X-Served-By": settings.edge_name}
    if result.warning:
        headers["Warning"] = result.warning

    return Response(content=result.data, media_type=result.content_type, headers=headers)
