import pymongo
from beanie import BeanieObjectId

from src.core.enums import LLMProvider, AnalysisStatus, AnalysisFailureKind
from src.models.mongo_base import BaseDocument
from src.schemas.analyses import AnalysisResult


class DocumentAnalysis(BaseDocument):
    id: BeanieObjectId
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
        indexes = [
            pymongo.IndexModel([("document_id", pymongo.ASCENDING), ("request_id", pymongo.ASCENDING)] , unique=True),
        ]
