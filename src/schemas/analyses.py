from pydantic import BaseModel, Field


class AnalysisResult(BaseModel):
    summary: str
    keywords: list[str]
    document_type: str
    entities: dict | None
    confidence: float = Field(ge=0.0, le=1.0)
    raw_response: str
