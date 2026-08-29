"""
Redis is the authoritative store for everything transient and high-speed:
matchmaking queues/locks, presence, WebSocket fan-out bookkeeping, and rate
limiting. Postgres never sees this traffic (see spec section 7).
"""
from redis.asyncio import Redis, from_url

from app.config.settings import get_settings

settings = get_settings()

_redis: Redis | None = None


def get_redis() -> Redis:
    """Singleton async Redis client (connection-pooled internally by redis-py)."""
    global _redis
    if _redis is None:
        _redis = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# --- Key namespaces (documented in one place so they never collide) ---
class RedisKeys:
    MATCHMAKING_POOL = "pairza:matchmaking:pool"  # sorted set: user_id -> joined_at score
    MATCHMAKING_LOCK = "pairza:matchmaking:lock"  # simple mutex around the pairing critical section
    PRESENCE = "pairza:presence"  # hash: user_id -> last_seen epoch
    SESSION_STATE = "pairza:session:{session_id}:state"  # mirrors authoritative status for fast reads
    RATE_LIMIT = "pairza:ratelimit:{scope}:{identity}"
