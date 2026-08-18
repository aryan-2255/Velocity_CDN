"""Fan-out of purge/invalidation pushes from Origin to every registered edge."""

import asyncio

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Edge


async def push_purge(db: AsyncSession, key: str) -> dict[str, str]:
    edges = (await db.execute(select(Edge).where(Edge.status != "disabled"))).scalars().all()
    if not edges:
        return {}

    async def purge_one(client: httpx.AsyncClient, edge: Edge) -> tuple[str, str]:
        try:
            resp = await client.post(f"{edge.base_url}/internal/purge/{key}")
            return edge.name, "ok" if resp.status_code < 400 else f"failed:{resp.status_code}"
        except httpx.HTTPError as exc:
            return edge.name, f"failed:{exc.__class__.__name__}"

    async with httpx.AsyncClient(timeout=settings.purge_timeout_seconds) as client:
        results = await asyncio.gather(*(purge_one(client, e) for e in edges))
    return dict(results)
