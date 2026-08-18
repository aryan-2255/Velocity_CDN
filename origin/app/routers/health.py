from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import settings
from app.db import get_db
from app.models import File

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict:
    """Origin's two hard dependencies are Postgres and S3, so both are probed
    here — an Origin that can't reach S3 still answers requests, it just fails
    every cache miss, which is worth seeing on the dashboard before users do."""
    try:
        await db.execute(text("select 1"))
        db_ok = True
    except Exception:
        db_ok = False

    s3_ok = await storage.bucket_reachable()

    file_count = total_bytes = None
    if db_ok:
        try:
            row = (await db.execute(select(func.count(File.id), func.sum(File.size_bytes)))).one()
            file_count, total_bytes = row[0], int(row[1] or 0)
        except Exception:
            pass

    return {
        "status": "healthy" if (db_ok and s3_ok) else "degraded" if db_ok or s3_ok else "unhealthy",
        "db": db_ok,
        "s3": s3_ok,
        "region": settings.s3_region,
        "bucket": settings.s3_bucket,
        "file_count": file_count,
        "total_bytes": total_bytes,
    }
