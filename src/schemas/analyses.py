from datetime import datetime

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider


class AnalysisResult(BaseModel):
    summary: str
    keywords: list[str]
    document_type: str
    entities: dict | None
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str


class AnalysisResponse(BaseModel):
    id: str
    provider: LLMProvider
    prompt_version: str | None = None
    result: AnalysisResult | None = None
    status: AnalysisStatus
    failure_kind: AnalysisFailureKind | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
    retry_of_analysis_id: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("id", mode="before")
    @classmethod
    def convert_id_to_str(cls, value: object) -> str:
        if isinstance(value, str):
            return value

        if isinstance(value, PydanticObjectId):
            return str(value)

        raise ValueError("Invalid analysis id")

    @field_validator("retry_of_analysis_id", mode="before")
    @classmethod
    def convert_retry_of_analysis_id_to_str(cls, value: object) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return value

        if isinstance(value, PydanticObjectId):
            return str(value)

        raise ValueError("Invalid retry_of_analysis_id")


class AnalysesListResponse(BaseModel):
    analyses: list[AnalysisResponse]
