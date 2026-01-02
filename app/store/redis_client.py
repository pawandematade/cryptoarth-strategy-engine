import redis
import os
from redis.exceptions import RedisError

redis_kwargs = {
    'host': os.environ["REDIS_HOST"],
    'port': int(os.environ.get("REDIS_PORT", 6379)),
    'db': int(os.environ.get("REDIS_DB", 0)),
    'decode_responses': True
}
if os.environ.get("REDIS_PASSWORD"):
    redis_kwargs['password'] = os.environ.get("REDIS_PASSWORD")

redis_client = redis.Redis(**redis_kwargs)


def test_connection():
    """
    Test Redis connection by pinging the server.
    
    Returns:
        bool: True if Redis is reachable, False if any exception occurs
    """
    try:
        redis_client.ping()
        return True
    except RedisError:
        return False
