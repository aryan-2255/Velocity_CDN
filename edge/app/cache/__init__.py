from app.cache.base import CachePolicy
from app.cache.fifo import FIFOPolicy
from app.cache.lfu import LFUPolicy
from app.cache.lru import LRUPolicy

POLICIES: dict[str, type[CachePolicy]] = {
    "lru": LRUPolicy,
    "lfu": LFUPolicy,
    "fifo": FIFOPolicy,
}


def build_policy(name: str) -> CachePolicy:
    try:
        return POLICIES[name]()
    except KeyError:
        raise ValueError(f"unknown cache policy '{name}', choose from {list(POLICIES)}") from None
