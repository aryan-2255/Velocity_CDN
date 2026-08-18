import time
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import Response

from app import origin_client
from app.config import DEFAULT_COORDS, REGION_COORDS, settings
from app.edge_registry import EdgeRegistry
from app.geoip import get_client_ip, resolve_ip
from app.routing import rank_edges

router = APIRouter(tags=["fetch"])


@router.get("/fetch/{key:path}")
async def fetch(key: str, request: Request, background_tasks: BackgroundTasks, region: str | None = None) -> Response:
    registry: EdgeRegistry = request.app.state.registry
    http_client: httpx.AsyncClient = request.app.state.http_client

    incoming_rid = request.headers.get("x-request-id")
    try:
        request_id = uuid.UUID(incoming_rid) if incoming_rid else uuid.uuid4()
    except ValueError:
        request_id = uuid.uuid4()

    client_ip = get_client_ip(request)

    if region is not None:
        coords = REGION_COORDS.get(region)
        if coords is None:
            raise HTTPException(status_code=400, detail=f"unknown region override '{region}', choose from {list(REGION_COORDS)}")
        lat, lon = coords
        resolved_region = region
        resolution_method = "manual_override"
    else:
        geo = resolve_ip(client_ip)
        if geo is not None:
            lat, lon, resolved_region = geo
            resolution_method = "geoip"
        else:
            lat, lon = DEFAULT_COORDS
            resolved_region = None
            resolution_method = "geoip_unresolved"

    candidates = rank_edges(lat, lon, registry.all())
    if not candidates:
        background_tasks.add_task(
            origin_client.log_request, http_client, settings.origin_base_url,
            request_id=request_id, client_ip=client_ip, resolved_region=resolved_region,
            resolution_method=resolution_method, edge_id=None, file_key=key,
            cache_result="error", latency_ms=0, status_code=503, bytes_served=None,
        )
        raise HTTPException(status_code=503, detail="no healthy edges available")

    start = time.perf_counter()

    for attempt, edge in enumerate(candidates):
        try:
            resp = await http_client.get(
                f"{edge.base_url}/content/{key}",
                headers={"X-Request-ID": str(request_id)},
                timeout=settings.edge_request_timeout_seconds,
            )
        except httpx.HTTPError:
            continue  # this edge is unreachable right now — fail over to the next-nearest

        if resp.status_code >= 500:
            continue  # edge is up but errored on this request — also fail over

        latency_ms = int((time.perf_counter() - start) * 1000)

        if resp.status_code == 404:
            background_tasks.add_task(
                origin_client.log_request, http_client, settings.origin_base_url,
                request_id=request_id, client_ip=client_ip, resolved_region=resolved_region,
                resolution_method=resolution_method, edge_id=edge.id, file_key=key,
                cache_result="error", latency_ms=latency_ms, status_code=404, bytes_served=None,
            )
            raise HTTPException(status_code=404, detail="file not found")

        cache_result = resp.headers.get("x-cache-result", "error")
        background_tasks.add_task(
            origin_client.log_request, http_client, settings.origin_base_url,
            request_id=request_id, client_ip=client_ip, resolved_region=resolved_region,
            resolution_method=resolution_method, edge_id=edge.id, file_key=key,
            cache_result=cache_result, latency_ms=latency_ms, status_code=resp.status_code,
            bytes_served=len(resp.content),
        )

        headers = {
            "X-Cache-Result": cache_result,
            "X-Served-By": edge.name,
            "X-Request-ID": str(request_id),
            "X-Failover": "true" if attempt > 0 else "false",
        }
        if resp.headers.get("warning"):
            headers["Warning"] = resp.headers["warning"]

        return Response(
            content=resp.content,
            media_type=resp.headers.get("content-type", "application/octet-stream"),
            headers=headers,
        )

    # Every candidate edge failed — origin-direct would be the next fallback
    # in a production CDN; out of scope for Phase 1 (edges are the only client-facing path).
    latency_ms = int((time.perf_counter() - start) * 1000)
    background_tasks.add_task(
        origin_client.log_request, http_client, settings.origin_base_url,
        request_id=request_id, client_ip=client_ip, resolved_region=resolved_region,
        resolution_method=resolution_method, edge_id=None, file_key=key,
        cache_result="error", latency_ms=latency_ms, status_code=502, bytes_served=None,
    )
    raise HTTPException(status_code=502, detail="all healthy edges failed to serve this request")
