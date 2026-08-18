"""Aggregate analytics for the dashboard. Every graph here is a GROUP BY over
request_logs / cache_events, no separate metrics store (see spec section 4)."""

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Edge, RequestLog

router = APIRouter(prefix="/internal/stats", tags=["stats"])


@router.get("/hit-ratio")
async def hit_ratio(db: AsyncSession = Depends(get_db)) -> dict:
    q = select(RequestLog.cache_result, func.count()).group_by(RequestLog.cache_result)
    rows = (await db.execute(q)).all()
    counts = {result or "unknown": count for result, count in rows}
    total = sum(counts.values())
    hits = counts.get("hit", 0)
    return {"counts": counts, "total": total, "hit_ratio": (hits / total) if total else 0.0}


@router.get("/hit-ratio-timeseries")
async def hit_ratio_timeseries(limit: int = 300, db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Cumulative hit ratio, one point per request.

    Deliberately not per-minute buckets. Bucketing breaks at both ends: a minute
    holding a single request plots as a hard 0% or 100%, so light traffic
    sawtooths, and filtering those out leaves an empty chart. A running total is
    defined from the very first request and smooths itself as the sample grows,
    which is also what "climbs from a cold start" actually describes.

    Returns at most `limit` points, sampled evenly, so a long run stays readable.
    """
    q = (
        select(RequestLog.ts, RequestLog.cache_result)
        .where(RequestLog.cache_result.in_(("hit", "miss", "stale")))
        .order_by(RequestLog.ts)
    )
    rows = (await db.execute(q)).all()
    if not rows:
        return []

    points = []
    hits = 0
    for i, (ts, result) in enumerate(rows, start=1):
        if result == "hit":
            hits += 1
        points.append({"ts": ts.isoformat(), "hit_ratio": hits / i, "total": i})

    # Even sampling keeps the shape while capping payload size.
    if len(points) > limit:
        step = len(points) / limit
        sampled = [points[int(i * step)] for i in range(limit)]
        sampled[-1] = points[-1]  # always keep the current value
        points = sampled
    return points


@router.get("/latency")
async def latency_by_result(db: AsyncSession = Depends(get_db)) -> list[dict]:
    q = (
        select(
            RequestLog.cache_result,
            RequestLog.resolved_region,
            func.avg(RequestLog.latency_ms),
            func.percentile_cont(0.5).within_group(RequestLog.latency_ms),
            func.percentile_cont(0.95).within_group(RequestLog.latency_ms),
            func.percentile_cont(0.99).within_group(RequestLog.latency_ms),
            func.count(),
        )
        .where(RequestLog.latency_ms.is_not(None))
        .group_by(RequestLog.cache_result, RequestLog.resolved_region)
    )
    rows = (await db.execute(q)).all()
    return [
        {
            "cache_result": result,
            "region": region,
            "avg_ms": round(float(avg), 1) if avg is not None else None,
            "p50_ms": round(p50, 1) if p50 is not None else None,
            "p95_ms": round(p95, 1) if p95 is not None else None,
            "p99_ms": round(p99, 1) if p99 is not None else None,
            "count": count,
        }
        for result, region, avg, p50, p95, p99, count in rows
    ]


@router.get("/top-files")
async def top_files(limit: int = 10, db: AsyncSession = Depends(get_db)) -> list[dict]:
    q = (
        select(RequestLog.file_key, func.count())
        .where(RequestLog.file_key.is_not(None))
        .group_by(RequestLog.file_key)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await db.execute(q)).all()
    return [{"file_key": key, "requests": count} for key, count in rows]


@router.get("/edge-requests")
async def requests_per_edge(db: AsyncSession = Depends(get_db)) -> list[dict]:
    q = (
        select(Edge.name, Edge.region, func.count(RequestLog.id))
        .join(RequestLog, RequestLog.edge_id == Edge.id, isouter=True)
        .group_by(Edge.name, Edge.region)
    )
    rows = (await db.execute(q)).all()
    return [{"edge": name, "region": region, "requests": count} for name, region, count in rows]
