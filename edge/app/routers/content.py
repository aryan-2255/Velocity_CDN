import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.config import settings
from app.origin_client import OriginNotFoundError, OriginUnreachableError

router = APIRouter(tags=["content"])

# Single range only ("bytes=0-1023", "bytes=500-", "bytes=-500"). Multipart
# ranges are legal HTTP but no browser needs them for media playback.
_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """Resolve a Range header to inclusive (start, end) byte offsets, or None if
    it's unusable. The caller treats None as 'ignore the header and send 200',
    which is what the spec allows for a range we can't satisfy sensibly."""
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None
    raw_start, raw_end = m.group(1), m.group(2)

    if raw_start == "" and raw_end == "":
        return None
    if raw_start == "":
        # suffix form: last N bytes
        length = int(raw_end)
        if length <= 0:
            return None
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
        end = min(end, size - 1)

    if start > end or start >= size:
        return None
    return start, end


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

    headers = {
        "X-Cache-Result": result.source,
        "X-Served-By": settings.edge_name,
        # Advertised unconditionally: the whole object is already in memory, so
        # any range is servable. Without this browsers won't attempt to seek.
        "Accept-Ranges": "bytes",
    }
    if result.warning:
        headers["Warning"] = result.warning

    size = len(result.data)
    range_header = request.headers.get("range")

    if range_header:
        span = _parse_range(range_header, size)
        if span is None:
            # Unsatisfiable: say so rather than silently sending everything, or
            # a media player will keep retrying the same bad range.
            if _RANGE_RE.match(range_header.strip()):
                return Response(
                    status_code=416,
                    headers={**headers, "Content-Range": f"bytes */{size}"},
                )
        else:
            start, end = span
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            return Response(
                content=result.data[start : end + 1],
                status_code=206,
                media_type=result.content_type,
                headers=headers,
            )

    return Response(content=result.data, media_type=result.content_type, headers=headers)
