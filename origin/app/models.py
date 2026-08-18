"""SQLAlchemy models mapped onto the schema owned by db/init.sql.

Tables are created by init.sql (run via psql in prod, auto-run by the Postgres
container locally) — this file does not call `Base.metadata.create_all`.
Keep it in sync with db/init.sql by hand; that file is the source of truth.
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Double, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class File(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    checksum: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Edge(Base):
    __tablename__ = "edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    region: Mapped[str] = mapped_column(String, nullable=False)
    base_url: Mapped[str] = mapped_column(String, nullable=False)
    lat: Mapped[float | None] = mapped_column(Double)
    lon: Mapped[float | None] = mapped_column(Double)
    status: Mapped[str] = mapped_column(String, nullable=False, default="unknown")
    cache_policy: Mapped[str] = mapped_column(String, nullable=False, default="lru")
    last_health_check: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    client_ip: Mapped[str | None] = mapped_column(String)
    resolved_region: Mapped[str | None] = mapped_column(String)
    resolution_method: Mapped[str | None] = mapped_column(String)
    edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("edges.id"))
    file_key: Mapped[str | None] = mapped_column(String)
    cache_result: Mapped[str | None] = mapped_column(String)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    status_code: Mapped[int | None] = mapped_column(Integer)
    bytes_served: Mapped[int | None] = mapped_column(BigInteger)


class CacheEvent(Base):
    __tablename__ = "cache_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("edges.id"))
    file_key: Mapped[str] = mapped_column(String, nullable=False)
    event_type: Mapped[str] = mapped_column(String, nullable=False)  # store | evict | expire | invalidate
    reason: Mapped[str | None] = mapped_column(String)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invalidation(Base):
    __tablename__ = "invalidations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    file_key: Mapped[str] = mapped_column(String, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    method: Mapped[str] = mapped_column(String, nullable=False)  # push | pull
    propagated_to: Mapped[dict | None] = mapped_column(JSONB)


class ChaosEvent(Base):
    __tablename__ = "chaos_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("edges.id"))
    action: Mapped[str] = mapped_column(String, nullable=False)  # kill | restore
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    latency_before_ms: Mapped[int | None] = mapped_column(Integer)
    latency_after_ms: Mapped[int | None] = mapped_column(Integer)
    failover_edge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("edges.id"))
