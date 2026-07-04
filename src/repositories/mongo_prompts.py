from redis.asyncio import Redis
import json
import structlog

from src.core.exceptions import ConflictError
from src.core.config import settings
from src.models.mongo_prompts import Prompt

logger = structlog.get_logger(__name__)


class MongoPromptsRepository:
    def __init__(self, redis_client: Redis):
        self.redis_client = redis_client

    async def get_active_prompt(self, prompt_type: str) -> Prompt | None:
        cache_key = f"cache:prompt:{prompt_type}:active"
        try:
            cache = await self.redis_client.get(cache_key)
            if cache:
                values = json.loads(cache)
                return Prompt(
                    version=values["version"],
                    prompt_type=prompt_type,
                    content=values["content"],
                    is_active=True
                )
        except Exception as err:
            logger.warning(
                "redis_unavailable_getting_cache_skipped",
                prompt_type=prompt_type,
                cache_key=cache_key,
                error=str(err),
            )
        prompt = await Prompt.find_one(Prompt.prompt_type == prompt_type, Prompt.is_active == True)
        if prompt:
            try:
                await self.redis_client.set(
                    cache_key,
                    json.dumps({"version": prompt.version, "content": prompt.content}),
                    ex=settings.cache.prompt_ttl,
                )
            except Exception as err:
                logger.warning(
                    "redis_unavailable_caching_skipped",
                    prompt_type=prompt_type,
                    cache_key=cache_key,
                    version=prompt.version,
                    error=str(err),
                )

        return prompt  # noqa: E712

    async def get_prompt_by_version(self, prompt_version: str) -> Prompt | None:
        return await Prompt.find_one(Prompt.version == prompt_version)

    async def create_prompt(self, version: str, prompt_type: str, content: str) -> Prompt:
        prompt_with_version = await self.get_prompt_by_version(version)

        if prompt_with_version:
            raise ConflictError()

        cache_key = f"cache:prompt:{prompt_type}:active"
        try:
            await self.redis_client.delete(cache_key)
        except Exception as err:
            logger.warning(
                "redis_unavailable_cache_invalidation_skipped",
                prompt_type=prompt_type,
                cache_key=cache_key,
                error=str(err),
            )

        active_prompt = await self.get_active_prompt(prompt_type)
        if active_prompt:
            active_prompt.is_active = False
            await active_prompt.save()
            logger.info(
                "prompt_deactivated",
                prompt_type=prompt_type,
                old_version=active_prompt.version,
                new_version=version,
            )

        new_prompt = Prompt(
            version=version,
            prompt_type=prompt_type,
            content=content,
            is_active=True,
        )

        await new_prompt.insert()

        return new_prompt
