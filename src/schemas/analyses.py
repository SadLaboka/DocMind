from datetime import datetime

from pydantic import BaseModel, Field

from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider


class AnalysisResult(BaseModel):
    summary: str
    keywords: list[str]
    document_type: str
    entities: dict | None
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str


class AnalysisResponse(BaseModel):
    document_id: int
    provider: LLMProvider
    prompt_version: str | None = None
    result: AnalysisResult | None = None
    analysis_status: AnalysisStatus
    failure_kind: AnalysisFailureKind | None = None
    error_code: str | None = None
    created_at: datetime
    updated_at: datetime
