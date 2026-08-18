# Benchmark results

Measured against the real AWS deployment on 2026-08-18 — Origin in us-east-1,
edges in ap-south-1 / eu-central-1 / ap-southeast-1, all on t4g.micro.

These are **smoke-test numbers from a hand-driven run**, not a Locust load
test. They're real measurements across real regions, but the sample is small
(141 requests) and the client was a single laptop in India rather than a
dedicated load generator. The Locust methodology below is still the thing to
run for publishable p99s under concurrency.

## Setup for this run

- **Client:** single laptop (India), driving `curl` against the Load Balancer's
  public IP in us-east-1. Region selection via the `?region=` manual override.
- **Files:** 5 × 80KB (`demo/file-00.txt` … `file-04.txt`) plus one 266KB file.
- **Workload:** Zipf-ish by hand — `file-00` requested 4× more often than the
  tail, 4 rounds × 3 regions × 11 requests.
- **Latency measured:** server-side, at the Load Balancer (`request_logs.latency_ms`)
  — LB → edge → response. Excludes the client's own hop to us-east-1, which
  would otherwise dominate and tell you about my ISP rather than the CDN.

## Results — latency by region and cache outcome

| Region | Outcome | n | p50 (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|---|---|
| Frankfurt (eu-central-1) | hit | 35 | **368** | 398 | 457 |
| Frankfurt (eu-central-1) | miss | 12 | 882 | 1045 | 1147 |
| Mumbai (ap-south-1) | hit | 35 | **742** | 810 | 844 |
| Mumbai (ap-south-1) | miss | 12 | 1709 | 2140 | 2415 |
| Singapore (ap-southeast-1) | hit | 37 | **854** | 902 | 908 |
| Singapore (ap-southeast-1) | miss | 12 | 1954 | 2320 | 2586 |

**Cache speedup (p50 miss ÷ p50 hit):** Frankfurt 2.4×, Mumbai 2.3×, Singapore 2.3×.

The distance ordering falls out of the data without being put there: Frankfurt
is closest to the us-east-1 Origin and pays the smallest miss penalty (882ms),
Singapore is furthest and pays the most (1954ms). A miss costs a round trip to
Virginia; a hit is served from the edge's own RAM.

| Metric | Value |
|---|---|
| Steady-state hit ratio | 74% (105 hits / 141 requests) |
| Entries cached per edge | 6 / 6 files |
| Origin fetches avoided | 105 of 141 requests (74%) |

## Cache policy comparison (SPEC.md section 8)

Each edge runs a different policy simultaneously — Mumbai=LRU, Frankfurt=LFU,
Singapore=FIFO — so one workload exercises all three.

| Policy | Edge | Hit Ratio |
|---|---|---|
| LRU | edge-mumbai | 74% |
| LFU | edge-frankfurt | 74% |
| FIFO | edge-singapore | 74% |

**These numbers are identical because the working set fits in cache.** All 6
files (~500KB total) fit comfortably under the 200MB cap, so nothing was ever
evicted, and with zero evictions all three policies are behaviourally the same.

This comparison only becomes meaningful once the working set exceeds capacity.
To make it a real experiment: either raise the file pool well past 200MB, or
drop `CACHE_MAX_BYTES` to a few hundred KB so eviction actually bites. Until
then, treat the table above as a demonstration that the policies are pluggable,
not as evidence about their relative performance.

## Chaos / failover test (SPEC.md section 12)

Verified against the live deployment:

1. **Baseline:** request with `?region=singapore` → served by `edge-singapore`,
   671ms (cache hit).
2. **Failure injected:** `docker stop edge` on the ap-southeast-1 instance.
3. **Detection:** Load Balancer's health-check loop marked `edge-singapore`
   `unhealthy` within ~25s.
4. **Failover:** next request with `?region=singapore` → automatically served by
   **`edge-mumbai`** (next-nearest by haversine distance), **557ms**, HTTP 200.
   No client-visible error.
5. **Recovery:** `docker start edge` → back to `healthy` within ~25s.

Failover latency was *lower* than baseline here (557ms vs 671ms) — Mumbai
happened to be closer to the measuring client than Singapore. That's an
artifact of measuring from India, not a general property; a client actually in
Singapore would see the expected penalty.

## Throughput — how many requests per second

Measured with a concurrent async client, run **on the instances themselves** so
the test client's own internet connection isn't what's being measured.

### Edge serving from cache (client on the edge box, no network in the path)

This is the application's own ceiling — one `uvicorn` worker on a t4g.micro
(2 vCPU, 1GB RAM), with the load generator competing for the same 2 vCPUs, so
these are conservative.

| File size | Concurrency | Throughput | Bandwidth | p50 | p99 |
|---|---|---|---|---|---|
| 23 B | 20 | **472 req/s** | — | 27 ms | 199 ms |
| 130 KB | 20 | **416 req/s** | 53 MB/s | 22 ms | 321 ms |

### Full path through the Load Balancer, cross-region

LB in us-east-1 → edge in eu-central-1 → back.

| Concurrency | Throughput | p50 | p99 |
|---|---|---|---|
| 10 | 96 req/s | 99 ms | 218 ms |
| 50 | 90 req/s | 510 ms | 1214 ms |

**Throughput does not improve past ~95 req/s — added concurrency only inflates
latency.** That's the signature of a network-bound system, not a CPU-bound one:
the ~90ms Atlantic round trip to Frankfurt dominates, so the LB is idle waiting
on the wire. At concurrency 10 the arithmetic is exactly 10 ÷ 0.1s ≈ 100 req/s.

### What this means

The edge can serve ~470 req/s; the cross-region hop caps the end-to-end path at
~95 req/s. **Scaling this would mean more edges closer to users, not bigger
instances** — which is the entire argument for a CDN, and here it's measured
rather than asserted.

Known ceilings, none of which have been hit yet:

- **Single uvicorn worker.** No `--workers` flag, so one process per service.
  On 2 vCPUs, 2–4 workers would plausibly double or triple the edge number.
- **t4g.micro network baseline.** "Up to 5 Gigabit" is burst credit, not
  sustained. Serving 1MB files at even 100 req/s is 800 Mbps — bandwidth, not
  CPU, becomes the wall for large assets.
- **Cache is in-process.** Restarting an edge empties it. Fine here; a real
  deployment would want a shared or persistent tier.

**For scale context:** 1,000,000 req/s is Cloudflare/Fastly territory — tens of
thousands of machines and custom networking. At 470 req/s per instance you'd
need roughly 2,100 of these boxes to reach it, ignoring coordination overhead
entirely. This project is a correct, measured CDN at small scale, and that's the
honest claim to make about it.

## Stale-while-revalidate, verified

Spec section 6 promises that an edge with an expired copy keeps serving when
Origin is unreachable. Tested directly with a throwaway edge configured at
`CACHE_TTL_SECONDS=5` (so the entry expires in seconds rather than five
minutes), against the local stack so the live deployment was untouched:

| Step | Origin | Cached copy | Result | Notes |
|---|---|---|---|---|
| 1 | up | none | `miss` | cold fetch |
| 2 | up | fresh | `hit` | inside TTL |
| 3 | up | **expired** | `miss` | revalidated normally — expiry alone is not "stale" |
| 4 | **down** | **expired** | **`stale`** | served old bytes + `Warning: 110 - Response is stale` |
| 5 | **down** | none | `502` | nothing to fall back to |
| 6 | back up | expired | `miss` | recovered, revalidates again |

Steps 4 and 5 are the pair that matters: same dead Origin both times. The key
the edge had seen before was still served; the key it had never seen returned
502. That is the entire value of retaining expired entries instead of evicting
at TTL.

Step 3 is the part people get wrong — **TTL expiry alone does not produce a
stale serve.** Stale requires both conditions: expired *and* Origin unreachable.

Edge counters afterwards read `hits=1 misses=2 stale_serves=1 errors=1` — stale
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
