import asyncio
import structlog
from beanie import BeanieObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.core.config import settings
from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider
from src.core.exceptions import ResourceNotFoundError, ServiceUnavailableError
from src.events.publisher import publish_document_analysis_requested
from src.models.mongo_analysis import DocumentAnalysis
from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.schemas.analyses import AnalysesListResponse, AnalysisResponse

logger = structlog.get_logger(__name__)


class AnalysisProviderError(Exception):
    pass


class AnalysisNotFoundError(Exception):
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
        """Gets or creates an analysis for a given document, request and provider"""

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

    async def get_analyses_list(
        self,
        document_id: int,
        limit: int = 10,
        page: int = 1,
        user_id: int | None = None,
        analyses_statuses: list[AnalysisStatus] | None = None,
        providers: list[LLMProvider] | None = None,
    ) -> AnalysesListResponse:
        """Gets a list of analyses for a given document and statuses"""

        skip = (page - 1) * limit

        analyses_list = await self.repository.get_analyses_by_document_id(
            document_id, limit=limit + 1, skip=skip, statuses=analyses_statuses, providers=providers
        )

        has_next = len(analyses_list) > limit

        analyses = AnalysesListResponse.model_validate(
            {"analyses": analyses_list[:limit], "limit": limit, "page": page, "has_next": has_next},
        )

        logger.info(
            "analyses_list_retrieved",
            user_id=user_id,
            document_id=document_id,
            statuses=analyses_statuses,
            providers=providers,
            page=page,
            limit=limit,
            has_next=has_next,
        )

        return analyses

    async def get_analysis(
        self,
        analysis_id: str,
        document_id: int,
        user_id: int | None = None,
    ) -> AnalysisResponse:
        """Gets an analysis for a given id and document id"""
        try:
            analysis_object_id = BeanieObjectId(analysis_id)
        except InvalidId as err:
            raise ResourceNotFoundError(
                error_code="analysis_not_found",
                message="Analysis not found",
                log_context={
                    "user_id": user_id,
                    "event_name": "get_analysis_failed",
                    "reason": "malformed_analysis_id",
                    "analysis_id": analysis_id,
                    "document_id": document_id,
                    "error_detail": getattr(err, "message", str(err)),
                },
            ) from err

        analysis = await self.repository.get_analysis_by_id_and_document_id(analysis_object_id, document_id)

        if not analysis:
            raise ResourceNotFoundError(
                error_code="analysis_not_found",
                message="Analysis not found",
                log_context={
                    "user_id": user_id,
                    "analysis_id": analysis_id,
                    "event_name": "get_analysis_failed",
                    "reason": "analysis_not_found",
                    "document_id": document_id,
                },
            )

        return AnalysisResponse.model_validate(analysis)

    async def create_and_dispatch_analysis(
            self,
            user_id: int,
            document_id: int,
            request_id: str,
            provider: LLMProvider | None = None,
    ) -> AnalysisResponse:
        """Creates and dispatches an analysis for a given document, request and provider"""

        if not provider:
            provider = LLMProvider(settings.llm.default_provider)

        logger.info(
            "analysis_creation_started",
            user_id=user_id,
            document_id=document_id,
            request_id=request_id,
            provider=provider.value,
        )

        analysis = await self.repository.create_analysis(document_id, request_id, provider)

        logger.info(
            "analysis_created",
            user_id=user_id,
            document_id=document_id,
            request_id=request_id,
            provider=provider.value,
        )

        try:

            logger.info(
                "analysis_dispatch_started",
                user_id=user_id,
                document_id=document_id,
                request_id=request_id,
                provider=provider.value,
            )

            await asyncio.to_thread(
                publish_document_analysis_requested,
                analysis_id=str(analysis.id),
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
            )

        except Exception as err:
            try:
                await self.mark_dispatch_failed(document_id=document_id, request_id=request_id, error_detail=err)
            except Exception as e:
                logger.warning(
                    "failed_mark_dispatch_failed",
                    request_id=request_id,
                    document_id=document_id,
                    user_id=user_id,
                    error_type=type(e).__name__,
                )
            raise ServiceUnavailableError(
                error_code="analysis_dispatch_failed",
                message="Analysis dispatch failed",
                log_context={
                    "user_id": user_id,
                    "document_id": document_id,
                    "error_type": type(err).__name__,
                }
            ) from err

        return AnalysisResponse.model_validate(analysis)

    async def mark_dispatch_failed(self, document_id: int, request_id: str, error_detail: Exception) -> None:
        """Marks analysis dispatch as failed"""

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
