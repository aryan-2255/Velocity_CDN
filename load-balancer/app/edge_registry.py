import asyncio
import logging
from dataclasses import dataclass, field

import httpx

from app import origin_client
from app.config import settings

logger = logging.getLogger("edge_registry")


@dataclass
class EdgeInfo:
    id: str
    name: str
    region: str
    base_url: str
    lat: float | None
    lon: float | None
    status: str
    cache_policy: str
    live: dict = field(default_factory=dict)  # latest /health body: occupancy, hit_ratio, etc.


class EdgeRegistry:
    """In-memory view of the edges table, kept fresh by two background loops:
    one re-reads the registry from Origin (picks up new/renamed edges), the
    other pings each edge's /health and writes status changes back to Origin
    (source of truth for edges.status lives in Postgres, but only Origin can
    write to it — see origin_client)."""

    def __init__(self, http_client: httpx.AsyncClient):
        self._http = http_client
        self._edges: dict[str, EdgeInfo] = {}
        self._lock = asyncio.Lock()

    def all(self) -> list[EdgeInfo]:
        return list(self._edges.values())

    def get(self, edge_id: str) -> EdgeInfo | None:
        return self._edges.get(edge_id)

    async def refresh_from_origin(self) -> None:
        try:
            rows = await origin_client.list_edges(self._http, settings.origin_base_url)
        except httpx.HTTPError as exc:
            logger.warning("failed to refresh edge registry from origin: %s", exc)
            return
        async with self._lock:
            for row in rows:
                existing = self._edges.get(row["id"])
                self._edges[row["id"]] = EdgeInfo(
                    id=row["id"], name=row["name"], region=row["region"], base_url=row["base_url"],
                    lat=row["lat"], lon=row["lon"], status=row["status"], cache_policy=row["cache_policy"],
                    live=existing.live if existing else {},
                )

    async def _check_one(self, edge: EdgeInfo) -> None:
        try:
            resp = await self._http.get(f"{edge.base_url}/health", timeout=settings.health_check_timeout_seconds)
            resp.raise_for_status()
            body = resp.json()
            new_status = "healthy"
        except httpx.HTTPError:
            body = {}
            new_status = "unhealthy"

        edge.live = body
        if new_status != edge.status:
            edge.status = new_status
            await origin_client.update_edge_status(self._http, settings.origin_base_url, edge.id, new_status)

    async def health_check_loop(self) -> None:
        while True:
            await asyncio.sleep(settings.health_check_interval_seconds)
            edges = self.all()
            if edges:
                await asyncio.gather(*(self._check_one(e) for e in edges), return_exceptions=True)

    async def refresh_loop(self) -> None:
        while True:
            await self.refresh_from_origin()
            await asyncio.sleep(settings.edge_refresh_interval_seconds)
