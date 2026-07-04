import structlog
from redis.asyncio import Redis

from src.core.redis import get_redis

logger = structlog.getLogger(__name__)


class TokenBlackList:
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    async def add_to_blacklist(self, jti: str, ttl: int) -> None:
        """Adds a jwt ID to the blacklist"""
        ttl = max(1, int(ttl))
        try:
            await self.redis.set(f"blacklist:{jti}", "1", ex=ttl)
        except Exception as err:
            logger.warning(
                "redis_unavailable_add_to_blacklist_skipped",
                jti=jti,
                error=str(err),
            )

    async def is_blacklisted(self, jti: str) -> bool:
        """Checks if the blacklisted jwt ID is in the blacklist"""
        try:
            return bool(await self.redis.exists(f"blacklist:{jti}"))
        except Exception as err:
            logger.warning(
                "redis_unavailable_blacklist_skipped",
                jti=jti,
                error=str(err),
            )
            return False


_token_blacklist: TokenBlackList | None = None


def get_token_blacklist() -> TokenBlackList:
    """Factory for creating a token black list instance"""
    global _token_blacklist
    if _token_blacklist is None:
        _token_blacklist = TokenBlackList(get_redis())
    return _token_blacklist
