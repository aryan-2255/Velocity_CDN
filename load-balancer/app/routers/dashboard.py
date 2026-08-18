"""Everything the dashboard talks to. Per the architecture diagram, the
Dashboard only ever calls the Load Balancer — analytics live in Origin's
Postgres, so these are thin passthroughs to Origin's /internal/* API."""

import asyncio
import json

import httpx
from fastapi import APIRouter, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import origin_client
from app.config import settings

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/logs/recent")
async def logs_recent(request: Request, since_id: int = 0, limit: int = 50) -> list[dict]:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_recent_logs(http_client, settings.origin_base_url, since_id, limit)


@router.get("/files")
async def list_files(request: Request) -> list[dict]:
    """What's actually available to fetch — lets the dashboard offer real keys
    instead of a hardcoded example that may not exist."""
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.list_files(http_client, settings.origin_base_url)


@router.post("/files")
async def upload_file(request: Request, upload: UploadFile, key: str | None = None) -> dict:
    """Passthrough to Origin's upload so the dashboard can add files without
    talking to Origin directly (the dashboard only ever calls the LB).

    Going through this path is what keeps S3 and the files table in step —
    writing to the bucket directly leaves no row, and every fetch for that key
    then 404s even though the bytes exist.
    """
    http_client: httpx.AsyncClient = request.app.state.http_client
    data = await upload.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"file is {len(data)} bytes, limit is {settings.max_upload_bytes}",
        )
    try:
        resp = await http_client.post(
            f"{settings.origin_base_url}/files",
            params={"key": key} if key else None,
            files={"upload": (upload.filename, data, upload.content_type or "application/octet-stream")},
            timeout=settings.upload_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"origin unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.delete("/files/{key:path}")
async def delete_file(request: Request, key: str) -> dict:
    """Deletes from S3 + DB and pushes a purge to every edge — the counterpart
    to upload, so the dashboard can clean up what it added."""
    http_client: httpx.AsyncClient = request.app.state.http_client
    try:
        resp = await http_client.delete(f"{settings.origin_base_url}/files/{key}", timeout=30.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"origin unreachable: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@router.get("/stats/hit-ratio")
async def stats_hit_ratio(request: Request) -> dict:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_stats(http_client, settings.origin_base_url, "hit-ratio")


@router.get("/stats/hit-ratio-timeseries")
async def stats_hit_ratio_timeseries(request: Request) -> list[dict]:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_stats(http_client, settings.origin_base_url, "hit-ratio-timeseries")


@router.get("/stats/latency")
async def stats_latency(request: Request) -> list[dict]:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_stats(http_client, settings.origin_base_url, "latency")


@router.get("/stats/top-files")
async def stats_top_files(request: Request, limit: int = 10) -> list[dict]:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_stats(http_client, settings.origin_base_url, "top-files", {"limit": limit})


@router.get("/stats/edge-requests")
async def stats_edge_requests(request: Request) -> list[dict]:
    http_client: httpx.AsyncClient = request.app.state.http_client
    return await origin_client.get_stats(http_client, settings.origin_base_url, "edge-requests")


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    """SSE live feed. Per-connection polling of Origin's recent-logs endpoint —
    honest request correlation, not a message bus. Fine at this scale."""
    http_client: httpx.AsyncClient = request.app.state.http_client

    async def event_generator():
        since_id = 0
        while True:
            if await request.is_disconnected():
                break
            try:
                rows = await origin_client.get_recent_logs(http_client, settings.origin_base_url, since_id, 50)
            except httpx.HTTPError:
                rows = []
            for row in reversed(rows):  # oldest first so the feed reads top-to-bottom in order
                since_id = max(since_id, row["id"])
                yield f"data: {json.dumps(row)}\n\n"
            await asyncio.sleep(1.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
