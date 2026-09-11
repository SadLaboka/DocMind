import structlog
from beanie import BeanieObjectId

from src.core.config import settings
from src.core.enums import AnalysisFailureKind, AnalysisStatus, PromptType
from src.events.schemas import AnalysisRequestedEvent
from src.llm.exceptions import LLMException
from src.llm.factory import LLMServiceFactory
from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.stream.consumers.base import BaseConsumer

logger = structlog.get_logger(__name__)

PROMPT_TYPE = PromptType.document_analysis.value


class ConsumerError(Exception):
    """Exception for consumer errors"""

    def __init__(self, message: str, retryable: bool = True, **kwargs) -> None:
        self.message = message
        self.retryable = retryable
        for key, value in kwargs.items():
            setattr(self, key, value)
        super().__init__(message)


class DocumentAnalysisConsumer(BaseConsumer[AnalysisRequestedEvent]):
    """FastStream consumer for analyzing extracted text"""

    def __init__(
        self,
        llm_service_factory: LLMServiceFactory,
        prompt_repo: MongoPromptsRepository,
        document_repo: MongoDocumentRepository,
        analysis_repo: MongoAnalysisRepository,
    ) -> None:
        self.prompt_repo = prompt_repo
        self.llm_service_factory = llm_service_factory
        self.document_repo = document_repo
        self.analysis_repo = analysis_repo

    def _get_event_model(self) -> type[AnalysisRequestedEvent]:
        return AnalysisRequestedEvent

    def _get_queue_name(self) -> str:
        return settings.rabbit.analysis_routing_key

    async def _on_final_failure(self, event: AnalysisRequestedEvent, error: Exception) -> None:
        """Changes analysis status after final failure"""

        try:
            await self.analysis_repo.update_analysis_fields(
                document_id=event.document_id,
                request_id=event.request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.transient,
                error_code=getattr(error, "error_code", "analysis_retries_exhausted"),
                error_detail=getattr(error, "message", str(error)),
            )
        except Exception as err:
            logger.error(
                "changing status after final failure failed",
                error_code="analysis_status_change_failed",
                error_detail="Final failure status changing failed",
                error_type=type(err).__name__,
                analysis_id=event.analysis_id,
                document_id=event.document_id,
                user_id=event.user_id,
                request_id=event.request_id,
            )

    async def handle(self, event: AnalysisRequestedEvent) -> None:  # type: ignore[override]
        """Main logic for analyzing extracted text"""
        analysis_id = event.analysis_id
        document_id = event.document_id
        user_id = event.user_id
        request_id = event.request_id

        try:
            analysis_object_id = BeanieObjectId(analysis_id)
        except Exception:
            raise ConsumerError(
                message="Invalid analysis id",
                retryable=False,
                error_code="invalid_analysis_id",
                error_detail="Invalid analysis id",
            )

        analysis = await self.analysis_repo.get_analysis_by_id(analysis_object_id)

        if not analysis:

            raise ConsumerError(
                retryable=False,
                message="Analysis not found",
                error_code="analysis_not_found",
                error_detail="Analysis with this document_id and request_id not found",
            )

        if analysis.status == AnalysisStatus.success or analysis.status == AnalysisStatus.failed:
            return

        if not (analysis.document_id == document_id and analysis.request_id == request_id):

            await self.analysis_repo.update_analysis_fields(
                document_id=analysis.document_id,
                request_id=analysis.request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.permanent,
                error_code="event_corrupted",
            )

            raise ConsumerError(
                message="event_corrupted",
                retryable=False,
                error_detail="Event has wrong document_id or request_id",
                error_code="event_corrupted",
            )

        content = await self.document_repo.get_content(document_id)

        if not content or not content.raw_text:
            logger.error(
                "document_text_not_found",
                error_code="analysis_text_not_found",
                error_detail="Raw text is missing in MongoDB",
                analysis_id=analysis_id,
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
            )

            await self.analysis_repo.update_analysis_fields(
                document_id=document_id,
                request_id=request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.permanent,
                error_code="document_text_not_found",
                error_detail="Raw text is missing in MongoDB",
            )

            return

        llm_service = self.llm_service_factory.create(analysis.provider.value)

        prompt = await self.prompt_repo.get_active_prompt(PROMPT_TYPE)
        if not prompt:
            raise ConsumerError(
                message="Active prompt not found",
                retryable=True,
                error_detail="Active prompt not found",
                error_code="prompt_not_found",
            )

        logger.info(
            "prompt_retrieved",
            analysis_id=analysis_id,
            document_id=document_id,
            user_id=user_id,
            request_id=request_id,
            prompt_version=prompt.version,
        )

        await self.analysis_repo.update_analysis_fields(
            document_id=document_id,
            request_id=request_id,
            status=AnalysisStatus.analyzing,
        )

        try:
            analysis_result = await llm_service.analyze_text(
                text=content.raw_text,
                prompt=prompt.content,
            )
        except LLMException as err:
            if err.retryable:
                raise

            logger.error(
                "llm_config_error",
                error_code=err.error_code,
                error_detail=err.message,
                analysis_id=analysis_id,
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
            )
            await self.analysis_repo.update_analysis_fields(
                document_id=document_id,
                request_id=request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.permanent,
                error_code=err.error_code,
                error_detail=err.message,
            )
            return

        await self.analysis_repo.update_analysis_fields(
            document_id=document_id,
            request_id=request_id,
            result=analysis_result,
            status=AnalysisStatus.success,
            prompt_version=prompt.version,
            error_code=None,
            error_detail=None,
            failure_kind=None,
        )

        logger.info(
            "document_analysis_completed",
            document_id=document_id,
            user_id=user_id,
            analysis_id=analysis_id,
            request_id=request_id,
            analysis_version=prompt.version,
        )
