import redis
from redis.exceptions import RedisError
from app.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

# Redis client connection using environment variables
# Include password if provided
redis_kwargs = {
    'host': REDIS_HOST,
    'port': REDIS_PORT,
    'db': 0,
    'decode_responses': True
}
if REDIS_PASSWORD:
    redis_kwargs['password'] = REDIS_PASSWORD

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


# To test this module in Python shell:
# python
# >>> from app.store.redis_client import redis_client, test_connection
# >>> test_connection()
# True  # or False if Redis is not running

