import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

from app.cache import build_policy
from app.cache_manager import CacheManager
from app.config import settings
from app.origin_client import register_edge
from app.routers import content, health, internal


@asynccontextmanager
async def lifespan(app: FastAPI):
    http_client = httpx.AsyncClient(timeout=settings.origin_timeout_seconds)
    app.state.http_client = http_client
    app.state.edge_id = None

    def get_edge_id():
        return app.state.edge_id

    policy = build_policy(settings.cache_policy)
    app.state.cache_manager = CacheManager(
        policy=policy,
        policy_name=settings.cache_policy,
        max_bytes=settings.cache_max_bytes,
        ttl_seconds=settings.cache_ttl_seconds,
        origin_base_url=settings.origin_base_url,
        http_client=http_client,
        edge_id_getter=get_edge_id,
    )

    async def register_with_retry():
        for _ in range(30):  # Origin may still be booting when this container starts
            edge_id = await register_edge(
                http_client, settings.origin_base_url,
                name=settings.edge_name, region=settings.region, base_url=settings.public_base_url,
                lat=settings.lat, lon=settings.lon, cache_policy=settings.cache_policy,
            )
            if edge_id is not None:
                app.state.edge_id = edge_id
                return
            await asyncio.sleep(2)

    registration_task = asyncio.create_task(register_with_retry())

    yield

    registration_task.cancel()
    await http_client.aclose()


app = FastAPI(title="Velocity CDN. Edge", lifespan=lifespan)

app.include_router(content.router)
app.include_router(internal.router)
app.include_router(health.router)
