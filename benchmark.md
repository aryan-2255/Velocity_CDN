# Benchmark results

Measured against the real AWS deployment on 2026-08-18. Origin in us-east-1,
edges in ap-south-1 / eu-central-1 / ap-southeast-1, all on t4g.micro.

These are **numbers from a scripted run, not a Locust load test.** Real
measurements across real regions over 541 requests, but the client was a single
laptop in India rather than a dedicated load generator in its own region. The
Locust methodology at the bottom is still what's needed for publishable p99s
under sustained concurrency.

## Setup for this run

- **Client:** single laptop (India) driving the Load Balancer's public IP in
  us-east-1, 12 concurrent requests, region chosen via the `?region=` override.
- **Files:** 9 assets, 23 B to 11.8 MB (images, JS, CSS, JSON, video).
- **Workload:** Zipf-ish. A hot set of 4 files takes ~70% of traffic, spread
  across 24 client cities.
- **Latency measured:** server-side at the Load Balancer
  (`request_logs.latency_ms`), covering LB to edge and back. Excludes the client's own
  hop to us-east-1, which would otherwise measure my ISP rather than the CDN.
- **Cold start:** edges restarted and `request_logs` truncated immediately
  before the run, so the hit ratio climbs from zero rather than resuming warm.

## Results, latency by cache outcome

| | p50 | p95 | n |
|---|---|---|---|
| **Cache hit** | **458 ms** | 1283 ms | 508 |
| **Cache miss** | 1620 ms | 3315 ms | 33 |

**Speedup: 3.5x at p50.**

## Results, per edge

| Edge | Region | Outcome | p50 | p95 | n |
|---|---|---|---|---|---|
| edge-frankfurt | eu-central-1 | hit | **284 ms** | 642 ms | 308 |
| edge-frankfurt | eu-central-1 | miss | 977 ms | 1497 ms | 14 |
| edge-mumbai | ap-south-1 | hit | 741 ms | 1418 ms | 85 |
| edge-mumbai | ap-south-1 | miss | 2009 ms | 3225 ms | 10 |
| edge-singapore | ap-southeast-1 | hit | 836 ms | 1530 ms | 115 |
| edge-singapore | ap-southeast-1 | miss | 2003 ms | 3614 ms | 9 |

The distance ordering falls out of the data without being put there: Frankfurt
is closest to the us-east-1 Origin and pays the smallest miss penalty (977ms),
Singapore is furthest and pays the most (2003ms). A miss costs a round trip to
Virginia; a hit is served from the edge's own RAM.

| Metric | Value |
|---|---|
| Steady-state hit ratio | 94% (508 hits / 541 requests) |
| Origin fetches avoided | 508 of 541 (94%) |
| Entries cached per edge | 8 of 9 files |

**Caveat on absolute numbers:** these include queueing from 12-way concurrency.
An earlier near-sequential run over 99 requests gave 218ms hit / 1152ms miss
(5.3x). Both are real; the contended run is published as the headline because
it's the more conservative claim and the larger sample.

## Throughput, how many requests per second

Measured with a concurrent async client, run **on the instances themselves** so
the test client's own internet connection isn't what's being measured.

### Edge serving from cache (client on the edge box, no network in the path)

This is the application's own ceiling: one `uvicorn` worker on a t4g.micro
(2 vCPU, 1GB RAM), with the load generator competing for the same 2 vCPUs, so
these are conservative.

| File size | Concurrency | Throughput | Bandwidth | p50 | p99 |
|---|---|---|---|---|---|
| 23 B | 20 | **472 req/s** | n/a | 27 ms | 199 ms |
| 130 KB | 20 | **416 req/s** | 53 MB/s | 22 ms | 321 ms |

### Full path through the Load Balancer, cross-region

LB in us-east-1 → edge in eu-central-1 → back.

| Concurrency | Throughput | p50 | p99 |
|---|---|---|---|
| 10 | 96 req/s | 99 ms | 218 ms |
| 50 | 90 req/s | 510 ms | 1214 ms |

**Throughput does not improve past ~95 req/s. Added concurrency only inflates
latency.** That's the signature of a network-bound system, not a CPU-bound one:
the ~90ms Atlantic round trip to Frankfurt dominates, so the LB is idle waiting
on the wire. At concurrency 10 the arithmetic is exactly 10 ÷ 0.1s ≈ 100 req/s.

### What this means

The edge can serve ~470 req/s; the cross-region hop caps the end-to-end path at
~95 req/s. **Scaling this would mean more edges closer to users, not bigger
instances**, which is the entire argument for a CDN, and here it's measured
rather than asserted.

Known ceilings, none of which have been hit yet:

- **Single uvicorn worker.** No `--workers` flag, so one process per service.
  On 2 vCPUs, 2–4 workers would plausibly double or triple the edge number.
- **t4g.micro network baseline.** "Up to 5 Gigabit" is burst credit, not
  sustained. Serving 1MB files at even 100 req/s is 800 Mbps, so bandwidth rather
  than CPU becomes the wall for large assets.
- **Cache is in-process.** Restarting an edge empties it. Fine here; a real
  deployment would want a shared or persistent tier.

**For scale context:** 1,000,000 req/s is Cloudflare/Fastly territory: tens of
thousands of machines and custom networking. At 470 req/s per instance you'd
need roughly 2,100 of these boxes to reach it, ignoring coordination overhead
entirely. This project is a correct, measured CDN at small scale, and that's the
honest claim to make about it.

## Single-flight, verified

Spec section 6 promises that N concurrent requests for the same uncached key
produce one Origin fetch, not N. Tested against the live deployment with a
freshly uploaded 400KB file that no edge had seen:

| Concurrent requests to edge-mumbai | Origin fetches |
|---|---|
| 25 | **1** |

Counted from Origin's own access log. Without the per-key `asyncio.Lock` in
`edge/app/cache_manager.py`, a cold-cache traffic spike becomes a thundering
herd against Origin: 25 duplicate S3 reads for one file.

All 25 are still logged as `miss`, which is correct: none were served from
cache. The saving is in Origin load, not in the labelling.

## Cache eviction, verified

Tested with a throwaway edge at `CACHE_MAX_BYTES=1000000` (1MB) and LRU, fed
five ~293KB files so the working set (1.47MB) exceeds the cap:

| Step | Entries | Occupancy | What happened |
|---|---|---|---|
| fetch ev/1 | 1 | 293 KB (29%) | stored |
| fetch ev/2 | 2 | 587 KB (59%) | stored |
| fetch ev/3 | 3 | 880 KB (88%) | stored |
| fetch ev/4 | 3 | 880 KB (88%) | **evicted ev/1**, stored ev/4 |
| fetch ev/5 | 3 | 880 KB (88%) | **evicted ev/2**, stored ev/5 |

Then re-requesting the two ends:

- `ev/1.txt` → **miss** (evicted, as LRU should)
- `ev/5.txt` → **hit** (most recent, survived)

**The cap was never exceeded.** Occupancy held at 880KB because a fourth
293KB entry would have crossed 1MB. `cache_events` recorded each eviction with
`reason=lru_evict`, so the policy that fired is attributable after the fact.

This is the test that makes the eviction-policy work real rather than
theoretical. Note the production edges run a 200MB cap against a ~15MB working
set, so **eviction never fires there**, which is exactly why the LRU/LFU/FIFO
hit-ratio comparison below is still not a meaningful experiment.

## Invalidation on update, verified

| Step | Result |
|---|---|
| Upload `inv-test.txt` as "VERSION ONE" | v1 |
| Fetch via mumbai and frankfurt | both serve "VERSION ONE", now cached |
| Re-upload same key as "VERSION TWO" | v2, new checksum |
| Fetch via mumbai, frankfurt, singapore | **all three serve "VERSION TWO"** |

`invalidations.propagated_to` recorded
`{"edge-mumbai": "ok", "edge-frankfurt": "ok", "edge-singapore": "ok"}`.

No edge served the stale copy after the update: the push purge beat the next
read, which is the property that matters. Per-edge success is tracked so a
partial propagation failure is visible rather than silent.

## Stale-while-revalidate, verified

Spec section 6 promises that an edge with an expired copy keeps serving when
Origin is unreachable. Tested directly with a throwaway edge configured at
`CACHE_TTL_SECONDS=5` (so the entry expires in seconds rather than five
minutes), against the local stack so the live deployment was untouched:

| Step | Origin | Cached copy | Result | Notes |
|---|---|---|---|---|
| 1 | up | none | `miss` | cold fetch |
| 2 | up | fresh | `hit` | inside TTL |
| 3 | up | **expired** | `miss` | revalidated normally, expiry alone is not "stale" |
| 4 | **down** | **expired** | **`stale`** | served old bytes + `Warning: 110 - Response is stale` |
| 5 | **down** | none | `502` | nothing to fall back to |
| 6 | back up | expired | `miss` | recovered, revalidates again |

Steps 4 and 5 are the pair that matters: same dead Origin both times. The key
the edge had seen before was still served; the key it had never seen returned
502. That is the entire value of retaining expired entries instead of evicting
at TTL.

Step 3 is the part people get wrong, **TTL expiry alone does not produce a
stale serve.** Stale requires both conditions: expired *and* Origin unreachable.

Edge counters afterwards read `hits=1 misses=2 stale_serves=1 errors=1`, stale
is tracked separately rather than folded into hits, so a healthy-looking hit
ratio can't quietly hide degraded serving.

## Still to run: Locust load test

The above is hand-driven. For publishable numbers under real concurrency:

- **Load generator:** `scripts/locustfile.py`, Zipf exponent `ZIPF_S = 1.1`,
  run from a 4th EC2 instance not co-located with any edge.
- **File sizes:** 10KB–1MB per master spec section 7 (bounds S3 egress cost).
- **Needed for a real policy comparison:** working set larger than
  `CACHE_MAX_BYTES`, per the note above.
- **Origin-direct baseline:** bypass the edges entirely to quantify what the
  cache layer buys.
