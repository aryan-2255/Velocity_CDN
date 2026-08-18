import asyncio
import logging
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError

from app.config import settings

logger = logging.getLogger("storage")


@lru_cache
def _client():
    kwargs: dict = {"region_name": settings.s3_region, "config": Config(signature_version="s3v4")}
    if settings.s3_endpoint_url:
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    if settings.aws_access_key_id and settings.aws_secret_access_key:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    return boto3.client("s3", **kwargs)


def _ensure_bucket_sync() -> None:
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        create_kwargs: dict = {"Bucket": settings.s3_bucket}
        if settings.s3_region != "us-east-1" and not settings.s3_endpoint_url:
            create_kwargs["CreateBucketConfiguration"] = {"LocationConstraint": settings.s3_region}
        client.create_bucket(**create_kwargs)


async def ensure_bucket() -> None:
    """Retries on startup — in docker-compose, MinIO's port can be open before
    it's actually ready to serve, and there's no strict service_healthy gate on it."""
    attempts = 15
    for attempt in range(1, attempts + 1):
        try:
            await asyncio.to_thread(_ensure_bucket_sync)
            return
        except EndpointConnectionError:
            if attempt == attempts:
                raise
            logger.warning("S3 endpoint not ready yet (attempt %d/%d), retrying...", attempt, attempts)
            await asyncio.sleep(2)


def _head_bucket_sync() -> bool:
    try:
        _client().head_bucket(Bucket=settings.s3_bucket)
        return True
    except Exception:
        return False


async def bucket_reachable() -> bool:
    """Cheap liveness probe for the health endpoint — head_bucket transfers no
    object data, so this is safe to call on every health check."""
    return await asyncio.to_thread(_head_bucket_sync)


def _put_sync(key: str, data: bytes, content_type: str) -> None:
    _client().put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)


def _get_sync(key: str) -> bytes:
    obj = _client().get_object(Bucket=settings.s3_bucket, Key=key)
    return obj["Body"].read()


def _delete_sync(key: str) -> None:
    _client().delete_object(Bucket=settings.s3_bucket, Key=key)


async def put_object(key: str, data: bytes, content_type: str) -> None:
    await asyncio.to_thread(_put_sync, key, data, content_type)


async def get_object(key: str) -> bytes:
    return await asyncio.to_thread(_get_sync, key)


async def delete_object(key: str) -> None:
    await asyncio.to_thread(_delete_sync, key)
