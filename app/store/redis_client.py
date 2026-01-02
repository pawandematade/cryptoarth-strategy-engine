import redis
import os

def get_redis_client():
    return redis.Redis(
        host=os.environ["REDIS_HOST"],
        port=int(os.environ.get("REDIS_PORT", 6379)),
        db=int(os.environ.get("REDIS_DB", 0)),
        decode_responses=True,
    )

redis_client = get_redis_client()
