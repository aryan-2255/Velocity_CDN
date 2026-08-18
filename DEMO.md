# Demo walkthrough

A script for recording a video, or for driving the live demo in an interview.
Roughly **4 minutes** if you talk while it runs. Every step below is something
the system actually does. Nothing here is staged.

**Setup:** dashboard open at the Load Balancer's address, one terminal window.

---

## 0. The one-sentence framing (15s)

> "This is a CDN I built from scratch: origin, edge caches, and the load
> balancer that routes between them. It's running on four AWS instances in four
> regions right now. The part I want to show is that the cache hit and miss
> numbers are real physics, not a simulation."

Don't say "CDN simulator". You built a CDN. It happens to be small.

---

## 1. Cold cache, the expensive path (45s)

Pick a city with **no local edge** (São Paulo is a good one) and a reasonably
large file like `assets/hero-banner.png`.

Click **Fetch**.

**Point at the result panel.** Say:

> "That's a miss. The edge in Frankfurt had never seen this file, so it had to
> go back to the origin in Virginia, which pulled it from S3. About a second."

**Why São Paulo matters:** there's no edge in South America. This is the case
where the router has to actually *decide* something: it ranked all three edges
by great-circle distance and picked Frankfurt. Say that out loud, because it's
the part that isn't configuration.

---

## 2. Warm cache, the whole point (30s)

Click **Fetch** again. Same file, same city. Don't change anything.

> "Same request. Now it's a hit, served out of the edge's RAM in Frankfurt.
> The origin never heard about this request at all."

**The number on screen dropped by roughly 5×.** Let the silence sit for a
second; the contrast does the work.

---

## 3. Geography is visible in the data (45s)

Scroll to **Avg latency by outcome, per region**.

> "Each bar pair is a city. The gap between hit and miss gets wider the further
> the client is from Virginia; Frankfurt is closest to the origin, so its miss
> penalty is smallest at around 866ms. Singapore is furthest and pays 1566ms.
> I didn't program that ordering. That's the speed of light through fibre,
> showing up in a Postgres table."

This is the strongest single moment in the demo. It's evidence the system is
physically distributed rather than three processes pretending.

---

## 4. Failover, kill a server on camera (60s)

This is the memorable part. Have the SSH command ready to paste.

```bash
# Terminal, stop the Singapore edge
ssh -i ~/.ssh/velocity-cache/edge-singapore.pem ubuntu@<singapore-ip> \
  'sudo docker stop edge'
```

> "I've just killed the Singapore edge. The load balancer health-checks every
> ten seconds, so give it a moment."

**Watch the Edge health panel go red.** Then pick **Sydney** in the dropdown
(Sydney normally routes to Singapore) and click Fetch.

> "Sydney's nearest edge is gone. The request still returns 200, but look at
> what served it: Mumbai. It walked down the distance-ranked list to the next
> healthy edge. The client never saw an error."

Bring it back:

```bash
ssh -i ~/.ssh/velocity-cache/edge-singapore.pem ubuntu@<singapore-ip> \
  'sudo docker start edge'
```

> "And it re-registers itself on boot. It comes back into rotation without me
> touching the database."

Note the edge comes back with an **empty cache**, which is correct: the cache
lives in process memory. Point that out rather than hoping nobody notices.

---

## 4b. Kill the Origin instead (45s, optional but strong)

Failover shows what happens when an *edge* dies. This shows what happens when
the thing everything depends on dies.

```bash
ssh -i ~/.ssh/velocity-cache/origin.pem ubuntu@<origin-ip> \
  'sudo docker stop origin'
```

**Point at the Infrastructure panel.** Origin goes red, and its `postgres` and
`s3` dots go with it. Now fetch a file the edge already has cached.

> "Origin is down. The whole source of truth is gone. But the edges still have
> their caches, so requests keep succeeding."

Then fetch something **no edge has cached**:

> "That one 502s, because there's nothing to fall back to. That's the honest
> boundary: a CDN can survive its origin dying only for content it
> already holds."

If you have time, the third case is the best one: an entry past its TTL with
origin down comes back as **stale** with a `Warning: 110` header, rather than
failing. It's the difference between "cache expired, so error" and "cache
expired, but stale beats nothing."

```bash
ssh -i ~/.ssh/velocity-cache/origin.pem ubuntu@<origin-ip> \
  'sudo docker start origin'
```

## 5. Real GeoIP (30s)

Switch the dropdown to **Auto (GeoIP)** and fetch.

> "No manual override now. That resolved my actual IP through a MaxMind
> database and routed on my real location."

Show the region column in the live feed reading an actual city name rather than
a dropdown value. If you want to prove it harder, the README has a table of six
real IPs from six countries and where each routes.

---

## 6. Close on the architecture (20s)

> "Four EC2 instances, four regions. The load balancer is my own FastAPI
> service. There's no AWS ALB in this account, because using one would replace
> the routing logic, which is the actual project. Same reason there's no
> CloudFront and no ElastiCache."

---

## Questions you'll get, and honest answers

**"Why not just use CloudFront?"**
> In production I would. The point of building it was to understand what
> CloudFront is doing: nearest-PoP selection, cache key handling, origin
> shielding, invalidation propagation. It's much easier to reason about a
> managed CDN after writing a small one.

**"What happens if 200 requests hit a cold key at once?"**
> One origin fetch, not 200. Each key has an `asyncio.Lock`: the first request
> fetches and the rest await the same in-flight result. Without it a cold-cache
> spike becomes a thundering herd against the origin.

**"How do you invalidate?"**
> Origin pushes `POST /internal/purge/{key}` to every edge on update or delete,
> and records per-edge success or failure in an `invalidations` table. Push
> rather than poll, because the propagation delay is what users actually notice.

**"Which eviction policy is best?"**
> Can't tell you from my data yet, and I'd rather say that than make it up. All
> three edges show the same hit ratio because my working set fits inside the
> cap, so nothing ever evicts, and with zero evictions the policies are
> behaviourally identical. To make it a real experiment I'd need the working set
> to exceed `CACHE_MAX_BYTES`. It's written up honestly in `benchmark.md`.

**"Is this production-ready?"**
> No, and the README says so. Plain HTTP, security groups open to the world, no
> auth on the admin endpoints. Fixing that means Nginx with TLS termination and
> auth-gated internal routes.

**"What happens if the origin goes down?"**
> Edges keep serving anything they've already cached, so most traffic is
> unaffected. Content no edge has cached returns 502, because there's nothing
> to serve.
> And an entry that's past its TTL gets served anyway with a `Warning: 110`
> header rather than failing, which is the stale-while-revalidate case. I tested
> all three; the table's in `benchmark.md`.

**"How many requests per second can it handle?"**
> An edge serves about 470 a second from cache on a t4g.micro. End to end through
> the load balancer it's about 95, and that's network-bound rather than
> CPU-bound. Adding concurrency past that only inflates latency, because the Atlantic round
> trip dominates. Which is the argument for the architecture: you scale it by
> putting edges closer to users, not by buying bigger instances. It's also
> single-worker uvicorn right now, so there's easy headroom I haven't taken.

**"Why is Postgres on the same box as Origin?"**
> Deliberate, and it's a real tradeoff. It keeps the metadata path on localhost
> with no network hop, but it means one instance dying takes both down and I own
> backups. RDS buys that isolation for an extra hop and another service. It's a
> connection-string change to migrate, same engine, so the cost of being wrong
> is low.

---

## Recording tips

- **1440px wide viewport.** The dashboard is responsive but the charts breathe
  better with room.
- **Warm one file before recording** so the hit-ratio chart isn't flat at zero,
  but leave the file you're demoing *cold* so step 1 is a genuine miss.
- **Don't cut the failover wait.** The ~25s of the health check noticing is the
  proof it's a real detection loop rather than a hardcoded delay.
- Dark mode records better on most displays. The dashboard follows your OS
  theme.
