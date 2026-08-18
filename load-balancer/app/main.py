import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_origin_list
from app.edge_registry import EdgeRegistry
from app.routers import dashboard, edges, fetch, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    http_client = httpx.AsyncClient()
    app.state.http_client = http_client

    registry = EdgeRegistry(http_client)
    app.state.registry = registry
    await registry.refresh_from_origin()

    refresh_task = asyncio.create_task(registry.refresh_loop())
    health_task = asyncio.create_task(registry.health_check_loop())

    yield

    refresh_task.cancel()
    health_task.cancel()
    await http_client.aclose()


app = FastAPI(title="Velocity CDN. Load Balancer", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide non-safelisted response headers from JS unless they're named
    # here, so without this the dashboard reads null for the cache result even
    # though the headers are on the wire (curl sees them fine).
    expose_headers=["X-Cache-Result", "X-Served-By", "X-Request-ID", "X-Failover", "Warning"],
)

app.include_router(fetch.router)
app.include_router(edges.router)
app.include_router(dashboard.router)
app.include_router(health.router)
