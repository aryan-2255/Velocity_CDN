import httpx


class OriginUnreachableError(Exception):
    """Origin timed out, refused the connection, or returned a 5xx."""


class OriginNotFoundError(Exception):
    """Origin is reachable and confirms the key does not exist."""


async def fetch_file(client: httpx.AsyncClient, origin_base_url: str, key: str) -> tuple[bytes, str]:
    try:
        resp = await client.get(f"{origin_base_url}/files/{key}")
    except httpx.HTTPError as exc:
        raise OriginUnreachableError(str(exc)) from exc

    if resp.status_code == 404:
        raise OriginNotFoundError(key)
    if resp.status_code >= 400:
        raise OriginUnreachableError(f"origin returned {resp.status_code}")

    return resp.content, resp.headers.get("content-type", "application/octet-stream")


async def register_edge(client: httpx.AsyncClient, origin_base_url: str, *, name: str, region: str,
                         base_url: str, lat: float, lon: float, cache_policy: str) -> str | None:
    """Best-effort self-registration. Returns the edge's UUID, or None if Origin isn't up yet."""
    try:
        resp = await client.post(
            f"{origin_base_url}/internal/edges/register",
            json={"name": name, "region": region, "base_url": base_url, "lat": lat, "lon": lon,
                  "cache_policy": cache_policy},
        )
        resp.raise_for_status()
        return resp.json()["id"]
    except httpx.HTTPError:
        return None


async def report_cache_event(client: httpx.AsyncClient, origin_base_url: str, *, edge_id: str | None,
                              file_key: str, event_type: str, reason: str | None) -> None:
    try:
        await client.post(
            f"{origin_base_url}/internal/logs/cache-event",
            json={"edge_id": edge_id, "file_key": file_key, "event_type": event_type, "reason": reason},
        )
    except httpx.HTTPError:
        pass  # logging must never break the request path
