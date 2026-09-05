from pymongo.errors import DuplicateKeyError

from src.core.enums import LLMProvider, AnalysisStatus, AnalysisFailureKind
from src.models.mongo_analysis import DocumentAnalysis
from src.repositories.mongo_analyses import MongoAnalysisRepository


class AnalysisProviderError(Exception):
    pass


class AnalysisNotFoundError(Exception):
    pass


class AnalysisStartError(Exception):
    pass


class AnalysisService:
    def __init__(self, analysis_repository: MongoAnalysisRepository) -> None:
        self.repository = analysis_repository

    async def get_or_create_analysis(
        self,
        document_id: int,
        request_id: str,
        provider: LLMProvider,
    ) -> DocumentAnalysis:

        analysis = await self.repository.get_analysis_by_document_and_request(document_id, request_id)

        if not analysis:
            try:
                analysis = await self.repository.create_analysis(document_id, request_id, provider)
            except DuplicateKeyError:
                analysis = await self.repository.get_analysis_by_document_and_request(document_id, request_id)

        if not analysis:
            raise AnalysisNotFoundError()

        if not analysis.provider == provider:
            raise AnalysisProviderError()

        return analysis

    async def mark_dispatch_failed(self, document_id: int, request_id: str, error_detail: Exception) -> None:

        analysis = await self.repository.get_analysis_by_document_and_request(document_id, request_id)

        if analysis and analysis.status == AnalysisStatus.queued:
            await self.repository.update_analysis_fields(
                document_id=document_id,
                request_id=request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.transient,
                error_code="analysis_dispatch_failed",
                error_detail=str(error_detail),
            )
