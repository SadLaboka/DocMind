import pymongo

from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider
from src.models.mongo_base import BaseDocument
from src.schemas.analyses import AnalysisResult


class DocumentAnalysis(BaseDocument):
    document_id: int
    request_id: str
    provider: LLMProvider
    prompt_version: str | None = None
    result: AnalysisResult | None = None
    status: AnalysisStatus = AnalysisStatus.queued
    failure_kind: AnalysisFailureKind | None = None
    error_code: str | None = None
    error_detail: str | None = None

    class Settings:
        name = "document_analyses"

        indexes = [
            pymongo.IndexModel([("document_id", pymongo.ASCENDING), ("request_id", pymongo.ASCENDING)], unique=True),
        ]
