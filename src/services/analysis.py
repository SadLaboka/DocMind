import asyncio

import structlog
from beanie import BeanieObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.core.config import settings
from src.core.enums import AnalysisFailureKind, AnalysisStatus, LLMProvider
from src.core.exceptions import ConflictError, ResourceNotFoundError, ServiceUnavailableError
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
        """Returns analysis response instance for a given id and document id"""
        analysis = await self._get_analysis_or_raise(analysis_id, document_id, user_id)

        return AnalysisResponse.model_validate(analysis)

    async def _get_analysis_or_raise(
        self,
        analysis_id: str,
        document_id: int,
        user_id: int | None = None,
    ) -> DocumentAnalysis:
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

        return analysis

    async def retry_analysis(
        self, analysis_id: str, document_id: int, request_id: str, user_id: int
    ) -> AnalysisResponse:
        """Retries failed analysis for a given analysis id"""

        analysis = await self._get_analysis_or_raise(analysis_id, document_id, user_id)

        if analysis.status != AnalysisStatus.failed or analysis.failure_kind != AnalysisFailureKind.transient:
            raise ConflictError(
                error_code="analysis_not_retryable",
                message="Analysis not retryable",
                log_context={
                    "event_name": "retry_analysis_failed",
                    "user_id": user_id,
                    "analysis_id": analysis_id,
                    "document_id": document_id,
                    "analysis_status": analysis.status.value,
                    "analysis_failure_kind": analysis.failure_kind.value if analysis.failure_kind else None,
                },
            )

        child_analysis = await self.repository.get_analysis_by_retry_of_analysis_id(analysis.id)

        if child_analysis:
            raise ConflictError(
                error_code="analysis_already_retried",
                message="Analysis already retried",
                log_context={
                    "event_name": "retry_analysis_failed",
                    "user_id": user_id,
                    "document_id": document_id,
                    "analysis_id": analysis_id,
                    "retried_analysis_id": str(child_analysis.id),
                },
            )

        try:

            logger.info(
                "create_retried_analysis",
                user_id=user_id,
                document_id=document_id,
                parent_analysis_id=analysis.id,
                provider=analysis.provider.value,
            )

            retried_analysis = await self.repository.create_analysis(
                document_id=document_id,
                request_id=request_id,
                provider=analysis.provider,
                retry_of_analysis_id=analysis.id,
            )
        except DuplicateKeyError as err:
            child_analysis = await self.repository.get_analysis_by_retry_of_analysis_id(analysis.id)

            if child_analysis:
                raise ConflictError(
                    error_code="analysis_already_retried",
                    message="Analysis already retried",
                    log_context={
                        "event_name": "retry_analysis_failed",
                        "user_id": user_id,
                        "document_id": document_id,
                        "analysis_id": analysis_id,
                        "retried_analysis_id": str(child_analysis.id),
                    },
                ) from err

            raise

        await self._dispatch_analysis(
            analysis_id=retried_analysis.id,
            document_id=retried_analysis.document_id,
            provider=retried_analysis.provider,
            request_id=retried_analysis.request_id,
            user_id=user_id,
        )

        return AnalysisResponse.model_validate(retried_analysis)

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
            provider=provider.value,
        )

        analysis = await self.repository.create_analysis(document_id, request_id, provider)

        logger.info(
            "analysis_created",
            user_id=user_id,
            document_id=document_id,
            analysis_id=str(analysis.id),
            provider=provider.value,
        )

        await self._dispatch_analysis(
            analysis_id=analysis.id,
            document_id=document_id,
            request_id=request_id,
            user_id=user_id,
            provider=provider,
        )

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

    async def remove_analysis(
            self,
            document_id: int,
            user_id: int,
            analysis_id: str
    ) -> AnalysisResponse:
        """Removes an analysis from the database by its analysis id"""

        logger.info(
            "analysis_remove_started",
            document_id=document_id,
            analysis_id=str(analysis_id),
            user_id=user_id,
        )

        analysis = await self._get_analysis_or_raise(analysis_id, document_id, user_id)

        if await self._check_analysis_child_exists(analysis.id):
            raise ConflictError(
                error_code="analysis_has_retry",
                message="Analysis has retry",
                log_context={
                    "event_name": "analysis_has_retry",
                    "reason": "analysis_has_child",
                    "document_id": document_id,
                    "analysis_id": analysis_id,
                    "user_id": user_id,
                }
            )

        if analysis.status not in (AnalysisStatus.failed, AnalysisStatus.success):
            raise ConflictError(
                error_code="analysis_in_progress",
                message="Analysis still in progress",
                log_context={
                    "event_name": "analysis_in_progress",
                    "reason": "analysis_status_not_failed_or_success",
                    "document_id": document_id,
                    "analysis_id": analysis_id,
                    "user_id": user_id,
                }
            )

        is_removed = await self.repository.remove_analysis_by_id(analysis.id)

        if not is_removed:
            raise ResourceNotFoundError(
                error_code="analysis_not_found",
                message="Analysis not found",
                log_context={
                    "user_id": user_id,
                    "analysis_id": analysis_id,
                    "event_name": "get_analysis_failed",
                    "reason": "analysis_not_found",
                    "document_id": document_id,
                }
            )

        logger.info(
            "analysis_removed",
            document_id=document_id,
            analysis_id=analysis_id,
            user_id=user_id,
        )

        return AnalysisResponse.model_validate(analysis)

    async def _check_analysis_child_exists(self, analysis_id: BeanieObjectId) -> bool:
        """Checks if analysis has a retry"""
        return bool(await self.repository.get_analysis_by_retry_of_analysis_id(analysis_id))

    async def _dispatch_analysis(
        self, analysis_id: BeanieObjectId, document_id: int, request_id: str, user_id: int, provider: LLMProvider
    ) -> None:
        """Dispatch analysis to queue"""
        try:

            logger.info(
                "analysis_dispatch_started",
                user_id=user_id,
                document_id=document_id,
                analysis_id=str(analysis_id),
                provider=provider.value,
            )

            await asyncio.to_thread(
                publish_document_analysis_requested,
                analysis_id=str(analysis_id),
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
                    document_id=document_id,
                    user_id=user_id,
                    error_type=type(e).__name__,
                )
            raise ServiceUnavailableError(
                error_code="analysis_dispatch_failed",
                message="Analysis dispatch failed",
                log_context={
                    "event_name": "analysis_dispatch_failed",
                    "user_id": user_id,
                    "provider": provider.value,
                    "document_id": document_id,
                    "error_type": type(err).__name__,
                },
            ) from err
