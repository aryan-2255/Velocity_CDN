from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import storage
from app.routers import files, health, internal, stats


@asynccontextmanager
async def lifespan(app: FastAPI):
    await storage.ensure_bucket()
    yield


app = FastAPI(title="Velocity CDN — Origin", lifespan=lifespan)

app.include_router(files.router)
app.include_router(internal.router)
app.include_router(stats.router)
app.include_router(health.router)
