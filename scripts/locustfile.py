"""Load generator for the Load Balancer's /fetch endpoint (master spec section 7).

Zipf-distributed key popularity is what makes eviction-policy differences show
up — a handful of files take most of the traffic, so LRU/LFU/FIFO disagree
about what to keep. Run from a box that is NOT co-located with any edge, so
you're measuring the system's latency, not your own loopback.

Usage:
    pip install locust
    locust -f scripts/locustfile.py --host http://localhost:8080

Then open http://localhost:8089, set concurrency, and go. For a scripted run:
    locust -f scripts/locustfile.py --host http://localhost:8080 \\
        --users 50 --spawn-rate 10 --run-time 5m --headless \\
        --csv scripts/results/run1

Seed demo files first: python3 scripts/seed_demo.py --count <FILE_POOL_SIZE below>
"""

import random

from locust import HttpUser, between, task

FILE_POOL_SIZE = 50  # must match (or be <=) --count passed to seed_demo.py
REGIONS = ["mumbai", "frankfurt", "singapore", None]  # None -> GeoIP, rest -> manual override

# Zipf exponent: higher = more skewed toward the popular few files. 1.0-1.2 is a
# realistic CDN-ish working set (a small number of files dominate traffic).
ZIPF_S = 1.1
_KEYS = [f"demo/file-{i:02d}.txt" for i in range(FILE_POOL_SIZE)]
_WEIGHTS = [1.0 / (rank ** ZIPF_S) for rank in range(1, FILE_POOL_SIZE + 1)]


def zipf_key() -> str:
    return random.choices(_KEYS, weights=_WEIGHTS, k=1)[0]


class CDNUser(HttpUser):
    wait_time = between(0.05, 0.4)

    @task
    def fetch_file(self):
        key = zipf_key()
        region = random.choice(REGIONS)
        params = {"region": region} if region else {}
        with self.client.get(f"/fetch/{key}", params=params, name="/fetch/[key]", catch_response=True) as resp:
            if resp.status_code >= 500:
                resp.failure(f"server error: {resp.status_code}")
            elif resp.status_code == 404:
                resp.failure("file not found — did you run scripts/seed_demo.py?")
            else:
                resp.success()
