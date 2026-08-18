import hashlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.db import get_db
from app.models import File, Invalidation
from app.purge import push_purge
from app.schemas import FileMetadata

router = APIRouter(prefix="/files", tags=["files"])


@router.post("", response_model=FileMetadata)
async def upload_file(
    upload: UploadFile,
    key: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> FileMetadata:
    object_key = key or upload.filename
    if not object_key:
        raise HTTPException(status_code=400, detail="key or filename required")

    data = await upload.read()
    checksum = hashlib.sha256(data).hexdigest()
    content_type = upload.content_type or "application/octet-stream"

    existing = (await db.execute(select(File).where(File.key == object_key))).scalar_one_or_none()

    await storage.put_object(object_key, data, content_type)

    if existing:
        existing.size_bytes = len(data)
        existing.content_type = content_type
        existing.checksum = checksum
        existing.version += 1
        existing.updated_at = datetime.now(timezone.utc)
        row = existing
    else:
        row = File(
            key=object_key,
            size_bytes=len(data),
            content_type=content_type,
            checksum=checksum,
        )
        db.add(row)

    await db.commit()
    await db.refresh(row)

    if existing:
        # Updated content invalidates whatever edges are already holding the old bytes.
        propagated = await push_purge(db, object_key)
        db.add(Invalidation(file_key=object_key, method="push", propagated_to=propagated))
        await db.commit()

    return FileMetadata.model_validate(row)


@router.get("", response_model=list[FileMetadata])
async def list_files(db: AsyncSession = Depends(get_db)) -> list[FileMetadata]:
    """Everything Origin knows about. Declared before the /{key:path} routes so
    the catch-all doesn't swallow it."""
    rows = (await db.execute(select(File).order_by(File.key))).scalars().all()
    return [FileMetadata.model_validate(r) for r in rows]


@router.get("/{key:path}/metadata", response_model=FileMetadata)
async def get_file_metadata(key: str, db: AsyncSession = Depends(get_db)) -> FileMetadata:
    row = (await db.execute(select(File).where(File.key == key))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="file not found")
    return FileMetadata.model_validate(row)


@router.get("/{key:path}")
async def get_file(key: str, db: AsyncSession = Depends(get_db)) -> Response:
    """Streams bytes from S3. Called by edges on cache miss, never directly by end users."""
    row = (await db.execute(select(File).where(File.key == key))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="file not found")
    try:
        data = await storage.get_object(key)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="failed to read from S3") from exc
    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            "ETag": row.checksum,
            "X-File-Version": str(row.version),
        },
    )


@router.delete("/{key:path}")
async def delete_file(key: str, db: AsyncSession = Depends(get_db)) -> dict:
    row = (await db.execute(select(File).where(File.key == key))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="file not found")

    await storage.delete_object(key)
    await db.delete(row)
    await db.commit()

    propagated = await push_purge(db, key)
    db.add(Invalidation(file_key=key, method="push", propagated_to=propagated))
    await db.commit()

    return {"key": key, "deleted": True, "propagated_to": propagated}
