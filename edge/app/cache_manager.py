import asyncio
import time
from dataclasses import dataclass
from typing import Literal

import httpx

from app.cache.base import CachePolicy
from app.origin_client import OriginNotFoundError, OriginUnreachableError, fetch_file, report_cache_event

CacheResultType = Literal["hit", "miss", "stale", "error"]


@dataclass
class CacheEntry:
    data: bytes
    content_type: str
    stored_at: float
    size: int


@dataclass
class CacheResult:
    data: bytes
    content_type: str
    source: CacheResultType
    warning: str | None = None


class CacheManager:
    """Owns the byte budget, TTL, and single-flight coordination for one edge's
    in-RAM cache. Eviction *choice* is delegated to a CachePolicy; everything
    about capacity, staleness, and concurrency lives here so swapping policies
    never touches this class (master spec section 8)."""

    def __init__(self, policy: CachePolicy, policy_name: str, max_bytes: int, ttl_seconds: int,
                 origin_base_url: str, http_client: httpx.AsyncClient, edge_id_getter):
        self._policy = policy
        self._policy_name = policy_name
        self._max_bytes = max_bytes
        self._ttl_seconds = ttl_seconds
        self._origin_base_url = origin_base_url
        self._http = http_client
        self._edge_id_getter = edge_id_getter  # callable returning current edge UUID (may be None early on)

        self._entries: dict[str, CacheEntry] = {}
        self._current_bytes = 0
        self._inflight: dict[str, asyncio.Task] = {}

        self.hits = 0
        self.misses = 0
        self.stale_serves = 0
        self.errors = 0

    # -- introspection for /health --------------------------------------
    @property
    def occupancy_bytes(self) -> int:
        return self._current_bytes

    @property
    def occupancy_pct(self) -> float:
        return (self._current_bytes / self._max_bytes) if self._max_bytes else 0.0

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    @property
    def hit_ratio(self) -> float:
        total = self.hits + self.misses + self.stale_serves
        return (self.hits / total) if total else 0.0

    # -- main path --------------------------------------------------------
    async def get(self, key: str) -> CacheResult:
        entry = self._entries.get(key)
        now = time.time()

        if entry is not None and (now - entry.stored_at) < self._ttl_seconds:
            self._policy.on_access(key)
            self.hits += 1
            return CacheResult(entry.data, entry.content_type, "hit")

        # Cold, or TTL-expired and needs revalidation — either way, single-flight the fetch.
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch_and_store(key))
            self._inflight[key] = task

        try:
            data, content_type = await task
        except OriginNotFoundError:
            self.errors += 1
            raise
        except OriginUnreachableError:
            if entry is not None:
                # stale-while-revalidate: origin down, but we have something to serve
                self._policy.on_access(key)
                self.stale_serves += 1
                return CacheResult(entry.data, entry.content_type, "stale", "110 - Response is stale")
            self.errors += 1
            raise
        finally:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

        self.misses += 1
        return CacheResult(data, content_type, "miss")

    async def _fetch_and_store(self, key: str) -> tuple[bytes, str]:
        data, content_type = await fetch_file(self._http, self._origin_base_url, key)
        await self._store(key, data, content_type)
        return data, content_type

    async def _store(self, key: str, data: bytes, content_type: str) -> None:
        size = len(data)

        if key in self._entries:
            self._current_bytes -= self._entries[key].size
            self._policy.on_remove(key)

        while self._current_bytes + size > self._max_bytes and self._entries:
            victim = self._policy.evict_candidate()
            if victim is None or victim not in self._entries:
                break
            self._current_bytes -= self._entries.pop(victim).size
            self._policy.on_remove(victim)
            await report_cache_event(
                self._http, self._origin_base_url, edge_id=self._edge_id_getter(),
                file_key=victim, event_type="evict", reason=f"{self._policy_name}_evict",
            )

        if size > self._max_bytes:
            # Larger than the whole cache — can't hold it. Serve it once but don't cache it.
            return

        self._entries[key] = CacheEntry(data=data, content_type=content_type, stored_at=time.time(), size=size)
        self._current_bytes += size
        self._policy.on_insert(key)
        await report_cache_event(
            self._http, self._origin_base_url, edge_id=self._edge_id_getter(),
            file_key=key, event_type="store", reason=None,
        )

    async def purge(self, key: str) -> bool:
        entry = self._entries.pop(key, None)
        if entry is None:
            return False
        self._current_bytes -= entry.size
        self._policy.on_remove(key)
        await report_cache_event(
            self._http, self._origin_base_url, edge_id=self._edge_id_getter(),
            file_key=key, event_type="invalidate", reason="manual_purge",
        )
        return True
