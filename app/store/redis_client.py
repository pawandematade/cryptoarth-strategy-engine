import redis
import os
from redis.exceptions import RedisError

# Build Redis connection kwargs strictly from environment
redis_kwargs = {
    "host": os.environ["REDIS_HOST"],   # REQUIRED
    "port": int(os.environ.get("REDIS_PORT", 6379)),
    "db": int(os.environ.get("REDIS_DB", 0)),
    "decode_responses": True,
}

# Optional password (ElastiCache usually doesn't need it)
if os.environ.get("REDIS_PASSWORD"):
    redis_kwargs["password"] = os.environ.get("REDIS_PASSWORD")

# Single Redis client (ONLY ONE SOURCE OF TRUTH)
redis_client = redis.Redis(**redis_kwargs)


def test_connection() -> bool:
    """
    Test Redis connection by pinging the server.
    """
    try:
        redis_client.ping()
        return True
    except RedisError:
        return False
