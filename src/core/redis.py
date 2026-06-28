from redis.asyncio import ConnectionPool, Redis

from src.core.config import settings

_redis_client: Redis | None = None


def get_redis() -> Redis:
    """Returns Redis client instance"""
    global _redis_client
    if _redis_client is None:
        pool = ConnectionPool(
            host=settings.redis.host,
            port=settings.redis.port,
            db=settings.redis.db,
            decode_responses=True,
            max_connections=settings.redis.max_connections,
        )
        _redis_client = Redis(connection_pool=pool)
    return _redis_client


async def init_redis() -> None:
    """Initialize Redis connection"""
    client = get_redis()
    await client.ping()


async def close_redis() -> None:
    """Close Redis connection"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
