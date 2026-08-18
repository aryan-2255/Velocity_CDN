-- Velocity Cache schema. Source of truth: origin/app/models.py mirrors these tables exactly.
-- This file is mounted into the Postgres container's /docker-entrypoint-initdb.d for local dev.
-- In production this is the script referenced by the handoff notes to run via `psql` on the Origin box.

create extension if not exists pgcrypto; -- gen_random_uuid()

-- Files: source-of-truth metadata (bytes live in S3)
create table files (
    id            uuid primary key default gen_random_uuid(),
    key           text unique not null,        -- S3 object key
    size_bytes    bigint not null,
    content_type  text not null,
    checksum      text not null,                -- sha256, used for invalidation checks
    version       int not null default 1,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

-- Edges: registry of edge nodes and live health
create table edges (
    id                 uuid primary key default gen_random_uuid(),
    name               text unique not null,     -- e.g. edge-mumbai
    region             text not null,
    base_url           text not null,
    lat                double precision,
    lon                double precision,
    status             text not null default 'unknown', -- healthy | unhealthy | unknown | disabled
    cache_policy       text not null default 'lru',       -- lru | lfu | fifo
    last_health_check  timestamptz
);

-- Request logs: every client request through the load balancer
create table request_logs (
    id                 bigserial primary key,
    request_id         uuid not null,            -- propagated across LB -> Edge -> Origin for correlation
    ts                 timestamptz not null default now(),
    client_ip          text,
    resolved_region    text,
    resolution_method  text,          -- geoip | manual_override
    edge_id            uuid references edges(id),
    file_key           text,
    cache_result       text,          -- hit | miss | stale | error
    latency_ms         integer,
    status_code        integer,
    bytes_served        bigint
);

-- Cache events: what each edge does to its own cache over time
create table cache_events (
    id          bigserial primary key,
    edge_id     uuid references edges(id),
    file_key    text not null,
    event_type  text not null,   -- store | evict | expire | invalidate
    reason      text,            -- lru_evict | lfu_evict | fifo_evict | ttl_expired | manual_purge
    ts          timestamptz not null default now()
);

-- Invalidation propagation tracking
create table invalidations (
    id              uuid primary key default gen_random_uuid(),
    file_key        text not null,
    triggered_at    timestamptz not null default now(),
    method          text not null,   -- push | pull
    propagated_to   jsonb            -- {"edge-mumbai": "ok", "edge-frankfurt": "failed"}
);

-- Chaos/failure test log (Phase 2)
create table chaos_events (
    id              bigserial primary key,
    edge_id         uuid references edges(id),
    action          text not null,     -- kill | restore
    ts              timestamptz not null default now(),
    latency_before_ms integer,
    latency_after_ms  integer,
    failover_edge_id  uuid references edges(id)
);

create index idx_request_logs_ts on request_logs(ts);
create index idx_request_logs_edge on request_logs(edge_id);
create index idx_request_logs_request_id on request_logs(request_id);
create index idx_cache_events_edge on cache_events(edge_id);
