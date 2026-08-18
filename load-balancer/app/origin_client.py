"""Origin is the only service with DB credentials, the LB reaches every
piece of persisted state (edge registry, request logs, analytics) through
Origin's /internal/* API (master spec section 4)."""

import uuid

import httpx


async def list_edges(client: httpx.AsyncClient, origin_base_url: str) -> list[dict]:
    resp = await client.get(f"{origin_base_url}/internal/edges")
    resp.raise_for_status()
    return resp.json()


async def update_edge_status(client: httpx.AsyncClient, origin_base_url: str, edge_id: str, status: str) -> None:
    try:
        await client.post(f"{origin_base_url}/internal/edges/{edge_id}/status", json={"status": status})
    except httpx.HTTPError:
        pass  # a failed status write shouldn't take down health checking


async def log_request(
    client: httpx.AsyncClient, origin_base_url: str, *,
    request_id: uuid.UUID, client_ip: str | None, resolved_region: str | None,
    resolution_method: str | None, edge_id: str | None, file_key: str | None,
    cache_result: str | None, latency_ms: int | None, status_code: int | None, bytes_served: int | None,
) -> None:
    try:
        await client.post(
            f"{origin_base_url}/internal/logs/request",
            json={
                "request_id": str(request_id),
                "client_ip": client_ip,
                "resolved_region": resolved_region,
                "resolution_method": resolution_method,
                "edge_id": edge_id,
                "file_key": file_key,
                "cache_result": cache_result,
                "latency_ms": latency_ms,
                "status_code": status_code,
                "bytes_served": bytes_served,
            },
        )
    except httpx.HTTPError:
        pass  # logging must never break the request path


async def list_files(client: httpx.AsyncClient, origin_base_url: str) -> list[dict]:
    resp = await client.get(f"{origin_base_url}/files")
    resp.raise_for_status()
    return resp.json()


async def get_recent_logs(client: httpx.AsyncClient, origin_base_url: str, since_id: int, limit: int) -> list[dict]:
    resp = await client.get(f"{origin_base_url}/internal/logs/recent", params={"since_id": since_id, "limit": limit})
    resp.raise_for_status()
    return resp.json()


async def get_stats(client: httpx.AsyncClient, origin_base_url: str, path: str, params: dict | None = None):
    resp = await client.get(f"{origin_base_url}/internal/stats/{path}", params=params or {})
    resp.raise_for_status()
    return resp.json()
