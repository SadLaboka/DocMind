import structlog
from beanie import BeanieObjectId

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.enums import DocumentStatus, PromptType, AnalysisStatus, AnalysisFailureKind
from src.events.schemas import AnalysisRequestedEvent
from src.llm.exceptions import LLMException
from src.llm.factory import LLMServiceFactory
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.stream.consumers.base import BaseConsumer

logger = structlog.get_logger(__name__)

PROMPT_TYPE = PromptType.document_analysis.value


class ConsumerError(Exception):
    """Exception for consumer errors"""

    def __init__(self, message: str, retryable: bool = True):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class DocumentAnalysisConsumer(BaseConsumer[AnalysisRequestedEvent]):
    """FastStream consumer for analyzing extracted text"""

    def __init__(self, llm_service_factory: LLMServiceFactory, prompt_repo: MongoPromptsRepository) -> None:
        self.prompt_repo = prompt_repo
        self.analysis_repo = MongoAnalysisRepository()
        self.llm_service_factory = llm_service_factory

    def _get_event_model(self) -> type[AnalysisRequestedEvent]:
        return AnalysisRequestedEvent

    def _get_queue_name(self) -> str:
        return settings.rabbit.extracted_routing_key

    async def handle(self, event: AnalysisRequestedEvent) -> None:  # type: ignore[override]
        """Main logic for analyzing extracted text"""
        analysis_id = event.analysis_id
        document_id = event.document_id
        user_id = event.user_id
        request_id = event.request_id

        analysis = await self.analysis_repo.get_analysis_by_id(BeanieObjectId(analysis_id))

        if not (analysis.document_id == document_id or analysis.request_id==request_id):

            await self.analysis_repo.update_analysis_fields(
                document_id=analysis.document_id,
                request_id=analysis.request_id,
                status=AnalysisStatus.failed,
                failure_kind=AnalysisFailureKind.transient,
                error_code="event_corrupted",
            )

            raise ConsumerError(
                message="event_corrupted",
                retryable=False,
            )


        llm_service = self.llm_service_factory.create(analysis.provider.value)

        prompt = await self.prompt_repo.get_active_prompt(PROMPT_TYPE)
        if not prompt:
            raise ConsumerError(
                message="Active prompt not found",
                retryable=True,
            )

        logger.info(
            "prompt_retrieved",
            analysis_id=analysis_id,
            document_id=document_id,
            user_id=user_id,
            request_id=request_id,
            prompt_version=prompt.version,
        )

        mongo_repo = MongoDocumentRepository()
        content = await mongo_repo.get_content(document_id)

        if not content or not content.raw_text:
            logger.error(
                "document_text_not_found",
                error_code="text_not_found",
                error_detail="Raw text is missing in MongoDB",
                analysis_id=analysis_id,
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
            )
            async with async_session_factory() as session:
                pg_repo = DocumentRepository(session)
                await pg_repo.update_document_fields(
                    document_id=document_id,
                    document_status=DocumentStatus.failed,
                    error_trace="Text not found in MongoDB after extraction",
                )
            return


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
        )

        logger.info(
            "document_analysis_completed",
            document_id=document_id,
            user_id=user_id,
            analysis_id=analysis_id,
            request_id=request_id,
            analysis_version=prompt.version,
        )
