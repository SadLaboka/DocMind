from datetime import datetime
from pydantic import BaseModel, field_validator, Field, ConfigDict
import re

from src.core.enums import PromptType


class PromptBase(BaseModel):
    prompt_type: PromptType
    version: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=100000)


class PromptRequest(PromptBase):
    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not re.match(r"^v\d+\.\d+\.\d+$", value):
            raise ValueError(f"Invalid version: {value}")
        return value

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if "{text}" not in value:
            raise ValueError("Invalid content: content must contain {text}")
        return value


class PromptResponse(PromptBase):
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
