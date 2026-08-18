from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    edge_name: str = "edge-mumbai"
    region: str = "ap-south-1"
    lat: float = 19.0760
    lon: float = 72.8777
    # Reachable by the Load Balancer / dashboard — matters most in docker-compose,
    # where each edge's own hostname differs from what it sees itself as.
    public_base_url: str = "http://edge-mumbai:8000"

    origin_base_url: str = "http://origin:8000"
    lb_base_url: str = "http://load-balancer:8000"  # unused directly, kept for symmetry/logging tools

    cache_policy: str = "lru"  # lru | lfu | fifo
    cache_max_bytes: int = 200 * 1024 * 1024  # 200MB hard cap — the whole point of an edge
    cache_ttl_seconds: int = 300

    origin_timeout_seconds: float = 10.0


settings = Settings()
