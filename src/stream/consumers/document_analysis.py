import structlog

from src.core.config import settings
from src.core.database import async_session_factory
from src.core.enums import DocumentStatus, PromptType
from src.events.schemas import DocumentTextExtractedEvent
from src.llm.exceptions import LLMException
from src.llm.factory import LLMServiceFactory
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.stream.consumers.base import BaseConsumer

logger = structlog.get_logger(__name__)

PROMPT_TYPE = PromptType.document_analysis.value


class ConsumerError(Exception):
    """Exception for consumer errors"""

    def __init__(self, message: str, retryable: bool = True):
        self.message = message
        self.retryable = retryable
        super().__init__(message)


class DocumentAnalysisConsumer(BaseConsumer[DocumentTextExtractedEvent]):
    """FastStream consumer for analyzing extracted text"""

    def __init__(self, llm_service_factory: LLMServiceFactory, prompt_repo: MongoPromptsRepository) -> None:
        self.prompt_repo = prompt_repo
        self.llm_service_factory = llm_service_factory

    def _get_event_model(self) -> type[DocumentTextExtractedEvent]:
        return DocumentTextExtractedEvent

    def _get_queue_name(self) -> str:
        return settings.rabbit.extracted_routing_key

    async def handle(self, event: DocumentTextExtractedEvent) -> None:  # type: ignore[override]
        """Main logic for analyzing extracted text"""
        document_id = event.document_id
        user_id = event.user_id
        request_id = event.request_id
        provider = event.provider

        llm_service = self.llm_service_factory.create(provider)

        prompt = await self.prompt_repo.get_active_prompt(PROMPT_TYPE)
        if not prompt:
            raise ConsumerError(
                message="Active prompt not found",
                retryable=True,
            )

        logger.info(
            "prompt_retrieved",
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
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
            )
            async with async_session_factory() as session:
                pg_repo = DocumentRepository(session)
                await pg_repo.update_document_fields(
                    document_id=document_id,
                    document_status=DocumentStatus.failed,
                    error_trace="Text not found in MongoDB",
                )
            return

        async with async_session_factory() as session:
            pg_repo = DocumentRepository(session)

            await pg_repo.update_document_fields(
                document_id=document_id,
                document_status=DocumentStatus.analyzing,
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
                    document_id=document_id,
                    user_id=user_id,
                    request_id=request_id,
                )
                await pg_repo.update_document_fields(
                    document_id=document_id,
                    document_status=DocumentStatus.failed,
                    error_trace=err.message,
                )
                return

            await mongo_repo.update_content(
                document_id=document_id,
                analysis=analysis_result.model_dump(),
                analysis_version=prompt.version,
            )

            await pg_repo.update_document_fields(
                document_id=document_id,
                document_status=DocumentStatus.success,
            )

            logger.info(
                "document_analysis_completed",
                document_id=document_id,
                user_id=user_id,
                request_id=request_id,
                analysis_version=prompt.version,
            )
