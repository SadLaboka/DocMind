from src.models.mongo_prompts import Prompt
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.core.enums import PromptType
import structlog

logger = structlog.get_logger(__name__)


class PromptService:
    def __init__(self, repository: MongoPromptsRepository):
        self.repository = repository

    async def create_prompt(self, version: str, prompt_type: PromptType, content: str) -> Prompt:
        """Creates a new prompt version and deactivates the previous active prompt"""
        logger.info("prompt_creation_initiated", prompt_type=prompt_type.value, version=version)

        prompt = await self.repository.create_prompt(version, prompt_type.value, content)

        logger.info("prompt_created", prompt_type=prompt_type.value, version=version)

        return prompt
