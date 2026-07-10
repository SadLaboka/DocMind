from fastapi import Depends

from src.services.prompts import PromptService
from src.core.redis import get_redis
from src.repositories.mongo_prompts import MongoPromptsRepository


def get_mongo_prompt_repository() -> MongoPromptsRepository:
    return MongoPromptsRepository(redis_client=get_redis())


def get_prompt_service(repository=Depends(get_mongo_prompt_repository)) -> PromptService:
    return PromptService(repository=repository)
