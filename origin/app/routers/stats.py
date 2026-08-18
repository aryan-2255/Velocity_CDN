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
async def hit_ratio_timeseries(
    bucket_minutes: int = 1, min_samples: int = 5, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Hit ratio over time, in time buckets.

    Buckets with fewer than `min_samples` requests are dropped: a minute holding
    one request plots as a hard 0% or 100% and reads as a dramatic swing, when
    it's a sample size of one. Without this the chart sawtooths on idle periods
    and buries the real trend.
    """
    bucket = func.date_trunc("minute", RequestLog.ts)
    q = (
        select(bucket.label("bucket"), RequestLog.cache_result, func.count())
        .group_by("bucket", RequestLog.cache_result)
        .order_by("bucket")
    )
    rows = (await db.execute(q)).all()
    buckets: dict[str, dict[str, int]] = {}
    for ts, result, count in rows:
        key = ts.isoformat()
        buckets.setdefault(key, {})[result or "unknown"] = count
    out = []
    for ts, counts in sorted(buckets.items()):
        total = sum(counts.values())
        if total < min_samples:
            continue
        hits = counts.get("hit", 0)
        out.append({"ts": ts, "hit_ratio": hits / total, "total": total})
    return out


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
