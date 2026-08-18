# Geo-Distributed Edge Caching System (CDN Simulator). Master Build Spec

## 1. What this is

A real CDN, not a mirror. One Origin holds the source of truth. Multiple Edge nodes deployed in genuinely different AWS regions hold a bounded, lazily-populated cache. A Load Balancer resolves client location (via GeoIP, with a manual override for demos) and routes to the nearest healthy edge. Cache misses pull from Origin, cache, then serve. Every request is logged and rendered on a live dashboard with real latency numbers.

Non-negotiable design rule: edges start empty and have a hard capacity cap. If an edge can hold every file, the cap is wrong.

Build in phases. Phase 1 is the core CDN and must work end-to-end before touching anything in Phase 2–4. Scope creep before Phase 1 ships is the most likely way this project dies.

---

## 2. Architecture

```
                         ┌─────────────────────┐
                         │      Dashboard        │
                         │  React + Tailwind +    │
                         │  Chart.js / SSE feed   │
                         └──────────┬─────────────┘
                                    │ REST + SSE
                                    ▼
                         ┌─────────────────────┐
              ┌──────────┤   Load Balancer       ├──────────┐
              │          │  FastAPI + GeoIP +     │          │
              │          │  health checks         │          │
              │          │  (behind Nginx: TLS     │          │
              │          │   termination only,    │          │
              │          │   routing logic stays   │          │
              │          │   in FastAPI)           │          │
              │          └──────────┬─────────────┘          │
              │                     │                          │
              ▼                     ▼                          ▼
      ┌──────────────┐     ┌──────────────┐          ┌──────────────┐
      │ Edge: Mumbai   │     │ Edge: Frankfurt│          │ Edge: Singapore│
      │ (ap-south-1)   │     │ (eu-central-1) │          │ (ap-southeast-1)│
      │ FastAPI +       │     │ FastAPI +       │          │ FastAPI +       │
      │ pluggable cache │     │ pluggable cache │          │ pluggable cache │
      │ (LRU/LFU/FIFO)  │     │ (LRU/LFU/FIFO)  │          │ (LRU/LFU/FIFO)  │
      └───────┬────────┘     └───────┬────────┘          └───────┬────────┘
              │  cache miss  →  fetch from Origin  ← ← ← ← ← ← ← ┘
              └──────────────────────┬──────────────────────────┘
                                      ▼
                         ┌─────────────────────┐
                         │       Origin           │
                         │  (us-east-1)           │
                         │  FastAPI + boto3       │
                         └──────┬──────────┬───────┘
                                │          │
                        ┌───────▼──┐   ┌───▼────────┐
                        │  AWS S3   │   │  PostgreSQL │
                        │  (files)  │   │  (installed │
                        │           │   │  directly   │
                        │           │   │  on Origin) │
                        └───────────┘   └─────────────┘
```

Every service (Origin, each Edge, Load Balancer) is a separate FastAPI process on its own EC2 instance. No service shares memory with another, that's what makes cache hits/misses real instead of simulated.

**Nginx's role, precisely:** TLS termination and reverse proxy in front of each FastAPI service. It does not make routing decisions. The geo-resolution and nearest-healthy-edge selection logic is the intellectual core of this project and stays in the Load Balancer's own FastAPI code, replacing it with Nginx upstream config deletes the thing worth explaining in an interview. If you want a visible "progression" story for the README, frame it as: Phase 1 ships with plain FastAPI (no TLS, local testing) → Phase 3 adds Nginx in front for TLS + connection handling, FastAPI keeps the routing brain the whole way through.

---

## 3. Regions and infra

| Component      | AWS Region       | Instance     | Notes                          |
|-----------------|-------------------|--------------|----------------------------------|
| Origin          | us-east-1 (N. Virginia) | t4g.micro | FastAPI + Docker + local PostgreSQL, talks to S3 |
| Edge 1          | ap-south-1 (Mumbai)      | t4g.micro | Pluggable in-RAM cache |
| Edge 2          | eu-central-1 (Frankfurt) | t4g.micro | Pluggable in-RAM cache |
| Edge 3          | ap-southeast-1 (Singapore) | t4g.micro | Pluggable in-RAM cache |
| Load Balancer   | co-locate with Origin or own t4g.nano | t4g.nano | Stateless, can restart freely |

- ARM Graviton (`t4g.*`) instances, cheaper, same free-tier eligibility.
- Docker Compose per box; one container per service.
- Nginx in front of each FastAPI service for TLS termination (Phase 3, see section 2).
- GitHub Actions: lint (ruff), test (pytest), build image on push to main.
- AWS Budget alert set at $50 before touching anything else.
- Do NOT use RDS, ALB, or CloudFront, they replace the exact components you're building.

---

## 4. Database. PostgreSQL, installed directly on Origin EC2

Origin talks to Postgres over localhost, no external network hop on the hot metadata path. Load Balancer and Edges never hold DB credentials directly, they report events to Origin/LB via API. Use SQLAlchemy (async, `asyncpg` driver).

Tradeoff worth knowing, and worth stating in your README: co-locating the DB with Origin means a Postgres crash or Origin redeploy takes metadata down with it, and you own backups (`pg_dump` on a cron, or a scheduled snapshot of the EBS volume). If you want that decoupled, a managed Postgres (RDS, or Supabase as a lighter-weight option) buys you that isolation at the cost of one more network hop and one more service to reason about. Either choice is defensible, the mistake is not knowing which tradeoff you made and why. Migrating from local Postgres to RDS later is a connection-string change, not a rewrite, since it's the same engine.

### Schema

See [db/init.sql](db/init.sql), kept as the single source of truth rather than duplicated here.

Every dashboard graph is a `GROUP BY` query against `request_logs` and `cache_events`. No separate metrics store needed for business-level metrics. System-level metrics (CPU/RAM/network per box) are a separate concern, see section 10.

---

## 5. Component specs

### 5.1 Origin (`origin/`)
- FastAPI service, stateless except for S3 + local Postgres.
- `POST /files`, multipart upload, writes bytes to S3, inserts row in `files`.
- `GET /files/{key}`, streams bytes from S3. Called by edges on cache miss, never directly by end users.
- `GET /files/{key}/metadata`, returns row from `files` (used for ETag/If-Modified-Since checks).
- `DELETE /files/{key}`, deletes from S3 + DB, writes to `invalidations`, pushes purge to all edges.
- `GET /health`, liveness.
- Bumps `files.version` and `checksum` on any update; this is what invalidation compares against.
- Propagates the inbound `X-Request-ID` header on every downstream/log call it makes (see section 9).

### 5.2 Edge (`edge-mumbai/`, `edge-frankfurt/`, `edge-singapore/`, same codebase, different config)
- In-RAM cache behind a single `CachePolicy` interface with three implementations: `LRUPolicy`, `LFUPolicy`, `FIFOPolicy`. Policy is selected per-edge via env var/config, swappable without touching routing or fetch logic. See section 8.
- Hard size cap (e.g. 200MB), TTL per entry, regardless of policy.
- `GET /content/{key}`:
  1. Check local cache. Hit → serve, log `cache_result=hit`.
  2. Miss → acquire an `asyncio.Lock` keyed by `key` (single-flight, prevents stampede) → fetch from Origin → store in cache (evict per active policy if over capacity) → serve, log `cache_result=miss`.
  3. If Origin unreachable and a stale (TTL-expired) copy exists → serve it with a `Warning` header (stale-while-revalidate), log `cache_result=stale`.
- `POST /internal/purge/{key}`. Origin calls this on delete/update; edge drops the entry, logs a `cache_events` row with `event_type=invalidate`.
- `GET /health`, returns status + current cache occupancy/hit-ratio for the LB's health check.
- Admin endpoints (Phase 3, auth-gated, see section 11): `POST /internal/admin/clear-cache`, `POST /internal/admin/disable`, `POST /internal/admin/enable`.

### 5.3 Load Balancer (`load-balancer/`)
- `GET /fetch/{key}`, main entry point.
  - Generates (or forwards, if already present) `X-Request-ID`, attaches it to every downstream call and log row.
  - Resolve region:
    - Default: GeoIP via MaxMind `GeoLite2-City.mmdb` + `geoip2` library, reading real client IP (trust only `TRUSTED_PROXIES`, never blind `X-Forwarded-For`).
    - Override: `?region=mumbai` (or a header) for manual testing/demo, hardcoded dropdown in the dashboard maps directly to this param.
  - Pick nearest **healthy, enabled** edge (haversine distance against `edges.lat/lon`, filtered by `status = healthy`).
  - Proxy request via `httpx`, time it, write a row to `request_logs`.
  - On edge failure: fail over to next-nearest healthy edge, log the extra latency separately so it's visible on the dashboard, and if triggered manually as a chaos test, write a `chaos_events` row (section 12).
- `GET /edges`, list all edges + live health for the dashboard.
- Background task: pings each edge's `/health` every N seconds, updates `edges.status`.

### 5.4 Dashboard (`frontend/`)
- React + Tailwind + Chart.js (or Recharts).
- Live request feed (SSE or 2s poll): timestamp, region, edge, hit/miss, latency, request ID (clickable, see section 9).
- Hit ratio over time (shows cold-start climb).
- Latency comparison: hit vs miss vs origin-direct, per region, bar chart.
- Top requested files, top regions, per-edge cache occupancy.
- Manual region selector (hardcoded dropdown) that sets the override param on `/fetch`.
- Edge health panel (green/red per edge), Phase 3 adds restart/clear-cache/disable/enable controls (section 11).
- Phase 4 adds the animated request-flow view (section 13).

---

## 6. Cache behavior, every scenario must be explicit

| Scenario | Behavior |
|---|---|
| Cold cache, first request | Miss, fetch from Origin, store, serve. Slow. |
| Warm cache | Hit, serve from RAM. Fast. |
| TTL expired, Origin reachable | Treated as miss, revalidate against Origin (`If-Modified-Since`/checksum), refresh or refetch. |
| TTL expired, Origin unreachable | Serve stale with `Warning` header (stale-while-revalidate), log `cache_result=stale`. |
| Cache full, new file arrives | Evict per active policy (LRU/LFU/FIFO), store new file, log `cache_events(event_type=evict, reason=<policy>_evict)`. |
| 200 concurrent requests, same uncached key | Single-flight: one fetch to Origin, 199 requests await the same in-flight future. |
| Origin deletes/updates a file | Origin pushes `POST /internal/purge/{key}` to every edge; failures are recorded in `invalidations.propagated_to`. |
| Edge fails health check | LB excludes it from routing, fails over, dashboard shows it red. |
| Edge manually disabled (admin console) | LB treats it as unavailable regardless of health check result. |

---

## 7. Benchmarking

- Load generator: Locust or k6, run from an EC2 instance in a fourth region (not co-located with any edge, to avoid measuring your own network).
- Workload: Zipf-distributed key popularity (a handful of files get most requests, this is what makes eviction policy differences visible) using small files (10KB–1MB) to avoid runaway S3 egress costs.
- Metrics to publish: p50/p95/p99 latency for hit / miss / origin-direct baseline, hit ratio at steady state, origin request volume with vs. without edge caching.
- These numbers go in the README's first paragraph, not buried at the bottom.
- Full methodology and results go in a separate `benchmark.md`, see section 14.

---

## 8. Cache policy comparison (Phase 2, highest value addition beyond core)

Implement `CachePolicy` as an interface (`should_evict()`, `on_access()`, `on_insert()`), with `LRUPolicy`, `LFUPolicy`, and `FIFOPolicy` as concrete implementations behind it. Edge selects one via config; no other code path changes.

Run the identical Zipf-distributed workload against each policy on the same edge (or one edge per policy for a simultaneous run), and record hit ratio for each in `benchmark.md`:

| Policy | Hit Ratio (example, replace with your real numbers) |
|---|---|
| LRU | |
| LFU | |
| FIFO | |

This is the difference between "I built a cache" and "I benchmarked cache replacement policies under a realistic access pattern." Do this before Phase 3's observability work, it has a far better value-to-effort ratio.

---

## 9. Request correlation (Phase 2, cheap)

`request_logs.request_id` already exists in the schema. Generate a UUID at the Load Balancer for each inbound request, pass it as `X-Request-ID` to the Edge, and have the Edge pass it to Origin on a cache miss. Every service logs the same ID. The dashboard gets a "trace view": click a request in the live feed, filter `request_logs` (and eventually `cache_events`) by that ID, and show the hop-by-hop timeline (LB → Edge → Origin → response).

This is honestly request correlation, not distributed tracing, don't oversell it as OpenTelemetry in your README. Full span-based tracing with Jaeger/OTel is a legitimate stretch goal but is not required to get the "click one request, see its journey" outcome.

---

## 10. Observability, system metrics (Phase 3)

Business metrics (hit ratio, requests/sec, latency) come from Postgres, already covered. CPU, RAM, and network per instance require scraping the OS, which your own logging cannot give you. Add:

- `node_exporter` on every EC2 instance (Origin, each Edge, LB).
- One Prometheus server scraping all `node_exporter` endpoints plus a custom `/metrics` endpoint on each FastAPI service (`prometheus-fastapi-instrumentator` is the standard library for this).
- Grafana on top of Prometheus for the ops-style dashboards (CPU, RAM, network, requests/sec per box).

Cost of this phase: three new services to deploy, configure, and keep alive. Budget real time for it and do it after Phase 1 and 2 are solid, not before. It is legitimate and companies do run this stack, but it is infrastructure, not novel engineering, don't let it eat the time budgeted for section 8.

---

## 11. Admin console (Phase 3)

Dashboard panel showing each edge with live status (🟢/🔴) and controls: **Clear Cache**, **Disable**, **Enable**. All three are safe to expose once behind auth.

**Do not expose "Restart" without authentication.** An HTTP endpoint that shells out to `systemctl restart` or `docker restart` is a real privilege-escalation surface if anyone can hit it. Put an API key or JWT check in front of every `/internal/admin/*` endpoint before building Restart, or drop Restart from the console and keep Clear Cache / Disable / Enable, which don't need to touch the process. If you do build Restart, document the auth requirement explicitly in your security section, that's a good thing to have said out loud in an interview, not just implemented.

---

## 12. Chaos / failure testing (Phase 2, cheap since failover already exists)

Manually mark an edge unhealthy (or actually kill the process) and record what the Load Balancer does:

1. Baseline: request routed to Singapore, measure latency.
2. Kill Singapore (`POST /internal/admin/disable` or stop the container).
3. Next request from the same client: LB detects failure, fails over to Frankfurt, measure latency.
4. Write both numbers to `chaos_events` and surface the before/after in the dashboard and `benchmark.md`.

Example from the README: latency before failure 19ms, latency after failover 142ms. That single measured pair does more for credibility than any amount of feature listing.

---

## 13. Architecture animation (Phase 4, demo polish, do last)

A visual on the dashboard that animates a request's path in real time: User → Load Balancer → Singapore → Cache Miss → Origin → S3 → Return → Cache Store. This has no engineering signal on its own, it's built entirely on data your system already produces (the request-correlation trail from section 9). Its value is in the README gif and the live demo, not in an interview answer. Build it last, after everything it visualizes actually works.

---

## 14. Deliverables beyond code

- `benchmark.md`, test setup (users, file size, region, duration), latency percentiles per scenario, hit/miss ratios, cache policy comparison table (section 8), chaos test results (section 12).
- Product name for the README instead of the literal system description (e.g. something like "Velocity Cache" or similar), costs nothing, do whenever, doesn't affect engineering.
- README opens with the one-paragraph pitch + the measured numbers, not a feature list.

---

## 15. Build order (milestones)

**Phase 1. Core CDN, must work end-to-end first**
1. Origin: upload + fetch a file end-to-end (S3 + Postgres `files` table). No cache yet.
2. One Edge: lazy cache, TTL, LRU eviction (default policy), single-flight. Prove hit vs miss against Origin.
3. Load Balancer: GeoIP resolution + manual override, route to the one edge, log to `request_logs`.
4. Add Edge 2 and Edge 3 in real AWS regions. Prove nearest-edge routing actually changes based on client IP.
5. Health checks + failover.
6. Invalidation: Origin push to all edges, track propagation.
7. Dashboard: live feed, hit ratio, latency graphs, health panel.
8. Load testing: Locust/k6 run, capture real p50/p95/p99, write them into the README.
9. Stale-while-revalidate on Origin failure, last in Phase 1, needs everything else working first.

**Phase 2, cheap, high value**
10. Cache policy comparison: LRU/LFU/FIFO behind one interface (section 8).
11. Request correlation via `X-Request-ID` (section 9).
12. Chaos/failover test with recorded before/after latency (section 12).
13. `benchmark.md` written up properly (section 14).

**Phase 3, real cost, real value, budget actual days**
14. Prometheus + Grafana for system metrics (section 10).
15. Admin console: clear cache / disable / enable, auth-gated (section 11).
16. Nginx in front of each service for TLS termination (section 2).

**Phase 4, polish, only if time remains**
17. Architecture animation on the dashboard (section 13).
18. Product naming + final README pass (section 14).

---

## 16. Access / handoff notes

- User will grant direct access (SSH/credentials) to Origin + all three Edge instances once provisioned.
- PostgreSQL to be installed directly on the Origin EC2 instance; schema in section 4 to be run there via `psql`.
- S3 bucket, IAM user (not root), and MaxMind GeoLite2 account/license key to be provisioned before Milestone 1.

---

## Implementation notes (this build)

This file is kept verbatim as the design reference. See [README.md](README.md)
for what's actually built and how to run it, and [benchmark.md](benchmark.md)
for results once a real load test has been run. Notable deltas from a literal
reading of this spec:

- Local dev substitutes MinIO for S3 and a Compose-managed Postgres for the
  "installed directly on Origin EC2" instance, both are env-var swaps, not
  code changes, once real AWS access lands (section 16).
- All three cache policies (LRU/LFU/FIFO) were implemented in Phase 1 rather
  than LRU-only, since the `CachePolicy` interface made the other two nearly
  free once written, but the actual *comparison* (identical Zipf workload,
  hit-ratio table) is still tracked as Phase 2 work per section 8.
- `request_logs.request_id` is populated from Phase 1 on (it's a NOT NULL
  column), but the dashboard's click-to-trace view described in section 9
  remains a Phase 2 UI feature, not yet built.
