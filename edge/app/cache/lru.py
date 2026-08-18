from collections import OrderedDict

from app.cache.base import CachePolicy


class LRUPolicy(CachePolicy):
    """Least-recently-used: evict the key that hasn't been touched the longest."""

    def __init__(self) -> None:
        self._order: OrderedDict[str, None] = OrderedDict()

    def on_insert(self, key: str) -> None:
        self._order[key] = None
        self._order.move_to_end(key)

    def on_access(self, key: str) -> None:
        if key in self._order:
            self._order.move_to_end(key)

    def on_remove(self, key: str) -> None:
        self._order.pop(key, None)

    def evict_candidate(self) -> str | None:
        if not self._order:
            return None
        return next(iter(self._order))
