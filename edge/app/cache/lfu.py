import itertools

from app.cache.base import CachePolicy


class LFUPolicy(CachePolicy):
    """Least-frequently-used: evict the lowest access count, oldest insertion breaks ties."""

    def __init__(self) -> None:
        self._freq: dict[str, int] = {}
        self._seq: dict[str, int] = {}
        self._counter = itertools.count()

    def on_insert(self, key: str) -> None:
        self._freq[key] = self._freq.get(key, 0) + 1
        self._seq[key] = next(self._counter)

    def on_access(self, key: str) -> None:
        if key in self._freq:
            self._freq[key] += 1

    def on_remove(self, key: str) -> None:
        self._freq.pop(key, None)
        self._seq.pop(key, None)

    def evict_candidate(self) -> str | None:
        if not self._freq:
            return None
        return min(self._freq, key=lambda k: (self._freq[k], self._seq[k]))
