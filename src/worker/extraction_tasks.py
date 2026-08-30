import asyncio
import time

import structlog

from src.core.enums import LLMProvider, DocumentStatus, MimeType
from src.core.database import celery_session_factory
from src.core.exceptions import ExtractionError
from src.core.mongo_database import init_mongo_for_worker
from src.events.publisher import publish_document_analysis_requested
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.services.extractors import TextExtractor
from src.services.analysis import AnalysisService
from src.worker.base_task import BaseTask
from src.worker.celery_app import app as celery_app


class DocumentExtractionTask(BaseTask):
    """Celery task to extract text from document"""

    def __init__(
        self, document_id: int, temp_path: str, mime_type: str, user_id: int, request_id: str, provider: str
    ) -> None:
        super().__init__(document_id, temp_path, mime_type, user_id, request_id, provider)
        self.extractor = TextExtractor()

    async def execute(self) -> None:
        """Main task manager"""
        structlog.contextvars.bind_contextvars(request_id=self.request_id)
        self.logger.info(
            "task_received_by_extraction_worker",
            user_id=self.user_id,
            document_id=self.document_id,
            mime_type=self.mime_type,
        )

        await init_mongo_for_worker()

        try:
            mime_enum = self._validate_mime_type()
        except ValueError as err:
            async with celery_session_factory() as session:
                repo = DocumentRepository(session)
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.failed,
                    error_trace=str(err),
                )
            raise

        async with celery_session_factory() as session:
            repo = DocumentRepository(session)

            if await self._is_document_cancelled(repo):
                return

            if not await self._is_path_exists(repo):
                return

            await repo.update_document_fields(self.document_id, document_status=DocumentStatus.extracting)

            await self._process_extraction(repo, mime_enum)

    def _validate_mime_type(self) -> MimeType:
        """Validates mime type"""
        if not self.mime_type:
            self.logger.error(
                "task_invalid_mime", document_id=self.document_id, user_id=self.user_id, reason="empty_mime_type"
            )
            self._cleanup_file()
            raise ValueError(f"mime_type is required for document {self.document_id}")

        try:
            return MimeType(self.mime_type)
        except ValueError:
            self.logger.error(
                "task_invalid_mime",
                document_id=self.document_id,
                reason="unsupported_mime",
                user_id=self.user_id,
                mime_type=self.mime_type,
            )
            self._cleanup_file()
            raise ValueError(f"Unsupported mime type: {self.mime_type}") from None

    async def _process_extraction(self, repo: DocumentRepository, mime_enum: MimeType) -> None:
        """Launch extraction logic"""

        mongo_repo = MongoDocumentRepository()
        analysis_repo = MongoAnalysisRepository()
        analysis_service = AnalysisService(analysis_repo)

        try:
            start_time = time.perf_counter()
            text = self.extractor.extract(self.temp_path, mime_enum)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            await mongo_repo.upsert_raw_text(
                document_id=self.document_id,
                raw_text=text,
            )

            await repo.update_document_fields(
                document_id=self.document_id,
                document_status=DocumentStatus.extracted,
                temp_filename=None,
            )

            self.logger.info(
                "text_extraction_completed",
                document_id=self.document_id,
                request_id=self.request_id,
                user_id=self.user_id,
                duration_ms=duration_ms,
                text_length=len(text),
            )

            analysis = await analysis_service.get_or_create_analysis(
                self.document_id,
                self.request_id,
                LLMProvider(self.provider)
            )

            analysis_id = str(analysis.id)

            self.logger.info(
                "analysis_created",
                analysis_id=analysis_id,
                document_id=self.document_id,
                request_id=self.request_id,
                provider=self.provider,
                user_id=self.user_id,
            )

            publish_document_analysis_requested(
                analysis_id=analysis_id,
                document_id=self.document_id,
                user_id=self.user_id,
                request_id=self.request_id,
            )

            self.logger.info(
                "document_analysis_request_published",
                document_id=self.document_id,
                user_id=self.user_id,
                request_id=self.request_id,
            )

            self._cleanup_file()

        except ExtractionError as err:
            if err.error_code == "file_not_found":
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.cancelled,
                    error_trace=str(err.log_context),
                    temp_filename=None,
                )
                self.logger.error(
                    "document_deleted_during_processing",
                    document_id=self.document_id,
                    user_id=self.user_id,
                    error_code=err.error_code,
                    error_detail=str(err.log_context),
                )
            else:
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.failed,
                    error_trace=str(err.log_context),
                    temp_filename=None,
                )
                self.logger.error(
                    "text_extraction_failed",
                    document_id=self.document_id,
                    user_id=self.user_id,
                    error_code=err.error_code,
                    error_detail=str(err.log_context),
                )
                self._cleanup_file()

        except Exception as err:
            self.logger.error(
                "transient_extraction_error",
                document_id=self.document_id,
                user_id=self.user_id,
                error_detail=str(err),
                exc_info=True,
            )
            raise


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    dont_autoretry_for=(ExtractionError, ValueError),
    task_acks_late=True,
    on_failure=DocumentExtractionTask._on_task_failure,
)
def extract_text_task(
    document_id: int,
    temp_path: str,
    mime_type: str,
    user_id: int,
    request_id: str,
    provider: str,
) -> None:
    """Runs a text extraction task async"""
    task = DocumentExtractionTask(
        document_id=document_id,
        temp_path=temp_path,
        mime_type=mime_type,
        user_id=user_id,
        request_id=request_id,
        provider=provider,
    )
    asyncio.run(task.execute())
