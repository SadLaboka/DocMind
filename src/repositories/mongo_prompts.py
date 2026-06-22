from src.core.exceptions import ConflictError
from src.models.mongo_prompts import Prompt


class MongoPromptsRepository:
    async def get_active_prompt(self, prompt_type: str) -> Prompt | None:
        return await Prompt.find_one(Prompt.prompt_type == prompt_type, Prompt.is_active == True)  # noqa: E712

    async def get_prompt_by_version(self, prompt_version: str) -> Prompt | None:
        return await Prompt.find_one(Prompt.version == prompt_version)

    async def create_prompt(self, version: str, prompt_type: str, content: str) -> Prompt:
        prompt_with_version = await self.get_prompt_by_version(version)

        if prompt_with_version:
            raise ConflictError()

        active_prompt = await self.get_active_prompt(prompt_type)
        if active_prompt:
            active_prompt.is_active = False
            await active_prompt.save()

        new_prompt = Prompt(
            version=version,
            prompt_type=prompt_type,
            content=content,
            is_active=True,
        )

        await new_prompt.insert()

        return new_prompt
