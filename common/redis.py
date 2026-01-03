"""
Redis Client - LAZY INITIALIZATION, NON-FATAL
Redis down → system UP
Connection created only when needed.
"""
import os
import logging
from redis import Redis
from redis.exceptions import ConnectionError
from typing import Optional

logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

_redis_client: Optional[Redis] = None

def get_redis() -> Optional[Redis]:
    """
    Get Redis client (LAZY INITIALIZATION)
    Returns None if Redis is unavailable - system continues to work
    """
    global _redis_client
    
    if not REDIS_HOST:
        # Redis not configured - return None (non-fatal)
        return None
    
    if _redis_client is None:
        try:
            _redis_client = Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True,
                socket_connect_timeout=3,
            )
            _redis_client.ping()
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis connection failed (non-fatal): {e}")
            _redis_client = None
            return None
    
    # Verify connection is still alive
    try:
        _redis_client.ping()
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis connection lost (non-fatal): {e}")
        _redis_client = None
        return None

# Backward compatibility: redis_client wrapper
# Existing code using redis_client will still work
class RedisClientWrapper:
    """Wrapper to maintain backward compatibility"""
    def __getattr__(self, name):
        client = get_redis()
        if client is None:
            # Return a no-op function for methods
            def noop(*args, **kwargs):
                logger.warning(f"Redis not available, {name}() called but ignored")
                return None
            return noop
        return getattr(client, name)
    
    def __call__(self, *args, **kwargs):
        return get_redis()
    
    def __bool__(self):
        return get_redis() is not None

redis_client = RedisClientWrapper()
