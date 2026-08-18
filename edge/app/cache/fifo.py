from collections import OrderedDict

from app.cache.base import CachePolicy


class FIFOPolicy(CachePolicy):
    """First-in-first-out: evict in insertion order, regardless of access pattern."""

    def __init__(self) -> None:
        self._order: OrderedDict[str, None] = OrderedDict()

    def on_insert(self, key: str) -> None:
        if key not in self._order:
            self._order[key] = None

    def on_access(self, key: str) -> None:
        pass  # access never changes eviction order under FIFO

    def on_remove(self, key: str) -> None:
        self._order.pop(key, None)

    def evict_candidate(self) -> str | None:
        if not self._order:
            return None
        return next(iter(self._order))
