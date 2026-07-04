import structlog
from redis.asyncio import Redis

from src.core.redis import get_redis
from src.core.config import settings

logger = structlog.getLogger(__name__)


class UserActiveStatusCache:
    def __init__(self, redis_client: Redis):
        self.redis = redis_client

    async def set_active(self, user_id: int, is_active: bool) -> None:
        """Set the user's status to cache"""
        key = f"user:{user_id}:is_active"
        await self.redis.set(key, is_active, ex=settings.cache.user_status_ttl)

    async def get_active(self, user_id: int) -> bool | None:
        """Get the user's status from cache"""
        key = f"user:{user_id}:is_active"

        return await self.redis.get(key)

_user_active_cache: UserActiveStatusCache | None = None


def get_user_active_cache() -> UserActiveStatusCache:
    """Factory for creating a user active status cache instance"""
    global _user_active_cache
    if _user_active_cache is None:
        _user_active_cache = UserActiveStatusCache(get_redis())
    return _user_active_cache
