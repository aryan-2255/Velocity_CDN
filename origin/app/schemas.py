import uuid
from datetime import datetime

from pydantic import BaseModel


class FileMetadata(BaseModel):
    id: uuid.UUID
    key: str
    size_bytes: int
    content_type: str
    checksum: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EdgeOut(BaseModel):
    id: uuid.UUID
    name: str
    region: str
    base_url: str
    lat: float | None
    lon: float | None
    status: str
    cache_policy: str
    last_health_check: datetime | None

    model_config = {"from_attributes": True}


class EdgeRegister(BaseModel):
    name: str
    region: str
    base_url: str
    lat: float | None = None
    lon: float | None = None
    cache_policy: str = "lru"


class EdgeStatusUpdate(BaseModel):
    status: str


class RequestLogIn(BaseModel):
    request_id: uuid.UUID
    client_ip: str | None = None
    resolved_region: str | None = None
    resolution_method: str | None = None
    edge_id: uuid.UUID | None = None
    file_key: str | None = None
    cache_result: str | None = None
    latency_ms: int | None = None
    status_code: int | None = None
    bytes_served: int | None = None


class CacheEventIn(BaseModel):
    edge_id: uuid.UUID | None = None
    file_key: str
    event_type: str
    reason: str | None = None


class ChaosEventIn(BaseModel):
    edge_id: uuid.UUID | None = None
    action: str
    latency_before_ms: int | None = None
    latency_after_ms: int | None = None
    failover_edge_id: uuid.UUID | None = None
