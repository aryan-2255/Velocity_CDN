from abc import ABC, abstractmethod


class CachePolicy(ABC):
    """Eviction-order bookkeeping only. Owns no bytes and no size math,
    CacheManager (cache_manager.py) is the only place that touches the byte
    budget or the actual entry store. Swapping policies never touches routing
    or fetch logic (master spec section 8)."""

    @abstractmethod
    def on_insert(self, key: str) -> None:
        """A new key was stored."""

    @abstractmethod
    def on_access(self, key: str) -> None:
        """An existing key was served from cache (a hit)."""

    @abstractmethod
    def on_remove(self, key: str) -> None:
        """A key left the cache (evicted, expired, or purged), drop internal state."""

    @abstractmethod
    def evict_candidate(self) -> str | None:
        """The key that should be evicted next, or None if the policy is empty."""
