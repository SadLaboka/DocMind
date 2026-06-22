from beanie import Indexed

from src.models.mongo_base import BaseDocument


class Prompt(BaseDocument):
    version: Indexed(str, unique=True)  # type: ignore
    prompt_type: Indexed(str)  # type: ignore
    content: str
    is_active: bool

    class Settings:
        name = "analysis_prompts"
