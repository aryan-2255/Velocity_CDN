"""Endpoints Origin exposes only to the Load Balancer and Edges.

Edges and the Load Balancer never hold Postgres credentials directly (see
master spec section 4), they report request/cache events here, and the LB
reads the edge registry + analytics through here too, since Origin is the
only service with a DB connection.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import CacheEvent, ChaosEvent, Edge, RequestLog
from app.schemas import (
    CacheEventIn,
    ChaosEventIn,
    EdgeOut,
    EdgeRegister,
    EdgeStatusUpdate,
    RequestLogIn,
)

router = APIRouter(prefix="/internal", tags=["internal"])


@router.get("/edges", response_model=list[EdgeOut])
async def list_edges(db: AsyncSession = Depends(get_db)) -> list[EdgeOut]:
    rows = (await db.execute(select(Edge))).scalars().all()
    return [EdgeOut.model_validate(r) for r in rows]


@router.post("/edges/register", response_model=EdgeOut)
async def register_edge(payload: EdgeRegister, db: AsyncSession = Depends(get_db)) -> EdgeOut:
    """Upsert-by-name so an edge can self-register on every boot without a manual INSERT."""
    row = (await db.execute(select(Edge).where(Edge.name == payload.name))).scalar_one_or_none()
    if row is None:
        row = Edge(name=payload.name, region=payload.region, base_url=payload.base_url,
                    lat=payload.lat, lon=payload.lon, cache_policy=payload.cache_policy,
                    status="unknown")
        db.add(row)
    else:
        row.region = payload.region
        row.base_url = payload.base_url
        row.lat = payload.lat
        row.lon = payload.lon
        row.cache_policy = payload.cache_policy
    await db.commit()
    await db.refresh(row)
    return EdgeOut.model_validate(row)


@router.post("/edges/{edge_id}/status", response_model=EdgeOut)
async def update_edge_status(edge_id: str, payload: EdgeStatusUpdate, db: AsyncSession = Depends(get_db)) -> EdgeOut:
    row = (await db.execute(select(Edge).where(Edge.id == edge_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="edge not found")
    row.status = payload.status
    row.last_health_check = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return EdgeOut.model_validate(row)


@router.post("/logs/request")
async def log_request(payload: RequestLogIn, db: AsyncSession = Depends(get_db)) -> dict:
    db.add(RequestLog(**payload.model_dump()))
    await db.commit()
    return {"ok": True}


@router.post("/logs/cache-event")
async def log_cache_event(payload: CacheEventIn, db: AsyncSession = Depends(get_db)) -> dict:
    db.add(CacheEvent(**payload.model_dump()))
    await db.commit()
    return {"ok": True}


@router.post("/logs/chaos-event")
async def log_chaos_event(payload: ChaosEventIn, db: AsyncSession = Depends(get_db)) -> dict:
    db.add(ChaosEvent(**payload.model_dump()))
    await db.commit()
    return {"ok": True}


@router.get("/logs/recent")
async def recent_logs(since_id: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)) -> list[dict]:
    q = select(RequestLog).where(RequestLog.id > since_id).order_by(RequestLog.id.desc()).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [
        {
            "id": r.id,
            "request_id": str(r.request_id),
            "ts": r.ts.isoformat(),
            "client_ip": r.client_ip,
            "resolved_region": r.resolved_region,
            "resolution_method": r.resolution_method,
            "edge_id": str(r.edge_id) if r.edge_id else None,
            "file_key": r.file_key,
            "cache_result": r.cache_result,
            "latency_ms": r.latency_ms,
            "status_code": r.status_code,
            "bytes_served": r.bytes_served,
        }
        for r in rows
    ]
