import pymongo
from beanie import BeanieObjectId

from src.core.enums import LLMProvider, AnalysisStatus, AnalysisFailureKind
from src.models.mongo_base import BaseDocument


class DocumentAnalysis(BaseDocument):
    id: BeanieObjectId
    document_id: int
    request_id: str
    provider: LLMProvider
    prompt_version: str | None = None
    result: str | None = None
    status: AnalysisStatus
    failure_kind: AnalysisFailureKind | None = None
    error_code: str | None = None
    error_detail: str | None = None

    class Settings:
        indexes = [
            pymongo.IndexModel([("document_id", pymongo.ASCENDING), ("request_id", pymongo.ASCENDING)] , unique=True),
        ]
