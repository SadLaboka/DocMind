from redis.asyncio import Redis
from time import time
from uuid import uuid4

from src.core.redis import get_redis


class RateLimiter:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    async def check_rate_limit(self, key: str, limit: int, window: int) -> tuple[bool, int, int]:
        """
        Checks if the rate limit is exceeded
        Returns False if the rate limit is exceeded, True if not
        Returns count of last requests
        Returns reset_time of the last request
        """

        current_time_ms = int(time() * 1000)
        window_start_ms = current_time_ms - window * 1000

        current_request = f"{current_time_ms}:{uuid4().hex[:8]}"

        async with self.redis.pipeline(transaction=True) as pipe:

            await pipe.zremrangebyscore(key, 0, window_start_ms)

            await pipe.zadd(key, {current_request: current_time_ms})

            await pipe.zcard(key)

            await pipe.expire(key, window)

            res = await pipe.execute()

        _, current_count, _, _ = res

        reset_time = current_time_ms // 1000 + window

        if current_count > limit:
            return False, current_count, reset_time
        return True, current_count, reset_time


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Factory for creating a rate limiter instance"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(get_redis())
    return _rate_limiter
