import asyncio
import time
from pathlib import Path

import structlog

from src.core.database import celery_session_factory
from src.core.exceptions import ExtractionError
from src.models.documents import DocumentStatus, MimeType
from src.repositories.documents import DocumentRepository
from src.services.extractors import TextExtractor
from src.worker.celery_app import app as celery_app

logger = structlog.get_logger(__name__)


class DocumentExtractionTask:
    """Celery task to extract text from document"""

    def __init__(self, document_id: int, temp_path: str, mime_type: str, request_id: str) -> None:
        self.document_id = document_id
        self.temp_path = Path(temp_path)
        self.mime_type = mime_type
        self.request_id = request_id
        self.extractor = TextExtractor()

    async def execute(self) -> None:
        """Main task manager"""
        structlog.contextvars.bind_contextvars(request_id=self.request_id)
        logger.info("task_received_by_worker", document_id=self.document_id, mime_type=self.mime_type)

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

            await repo.update_document_fields(self.document_id, document_status=DocumentStatus.extracting)

            await self._process_extraction(repo, mime_enum)

    @staticmethod
    def _on_task_failure(exc, task_id, args, kwargs, _einfo) -> None:
        """
        Celery callback for on_failure
        Called after all retries have been exhausted
        Does not delete the tempo file here to allow manual restarts
        """
        document_id = kwargs.get("document_id")
        if document_id:
            logger.error(
                "task_final_failure",
                document_id=document_id,
                task_id=task_id,
                error_detail=str(exc),
            )
            asyncio.run(DocumentExtractionTask._update_status_after_failure(document_id, str(exc)))

    @staticmethod
    async def _update_status_after_failure(document_id: int, error_detail: str) -> None:
        """Updates document status after final failure"""
        async with celery_session_factory() as session:
            repo = DocumentRepository(session)
            current_doc = await repo.get_document_by_id(document_id)

            if current_doc and current_doc.document_status != DocumentStatus.cancelled:
                await repo.update_document_fields(
                    document_id=document_id,
                    document_status=DocumentStatus.failed,
                    error_trace=f"Task failed after all retries: {error_detail}",
                )

    def _validate_mime_type(self) -> MimeType:
        """Validates mime type"""
        if not self.mime_type:
            logger.error("task_invalid_mime", document_id=self.document_id, reason="empty_mime_type")
            self._cleanup_file()
            raise ValueError(f"mime_type is required for document {self.document_id}")

        try:
            return MimeType(self.mime_type)
        except ValueError:
            logger.error(
                "task_invalid_mime",
                document_id=self.document_id,
                reason="unsupported_mime",
                mime_type=self.mime_type,
            )
            self._cleanup_file()
            raise ValueError(f"Unsupported mime type: {self.mime_type}")

    async def _is_document_cancelled(self, repo: DocumentRepository) -> bool:
        """Checks whether document processing has been canceled"""
        current_doc = await repo.get_document_by_id(self.document_id)
        if not current_doc or current_doc.document_status == DocumentStatus.cancelled:
            logger.info("document_cancelled_or_deleted", document_id=self.document_id)
            self._cleanup_file()
            return True
        return False

    async def _process_extraction(self, repo: DocumentRepository, mime_enum: MimeType) -> None:
        """Launch extraction logic"""
        try:
            start_time = time.perf_counter()
            text = self.extractor.extract(self.temp_path, mime_enum)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            await repo.update_document_fields(
                document_id=self.document_id,
                document_text=text,
                document_status=DocumentStatus.extracted,
                temp_filename=None,
            )

            logger.info(
                "text_extraction_completed",
                document_id=self.document_id,
                duration_ms=duration_ms,
                text_length=len(text),
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
                logger.error(
                    "document_deleted_during_processing",
                    document_id=self.document_id,
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
                logger.error(
                    "text_extraction_failed",
                    document_id=self.document_id,
                    error_code=err.error_code,
                    error_detail=str(err.log_context),
                )
                self._cleanup_file()

        except Exception as err:
            logger.error(
                "transient_extraction_error",
                document_id=self.document_id,
                error_detail=str(err),
                exc_info=True,
            )
            raise

    def _cleanup_file(self) -> None:
        """Safely cleanup file"""
        if self.temp_path.exists():
            self.temp_path.unlink(missing_ok=True)


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    exclude_exceptions=(ExtractionError, ValueError),
    task_acks_late=True,
    on_failure=DocumentExtractionTask._on_task_failure,
)
def extract_text_task(document_id: int, temp_path: str, mime_type: str, request_id: str) -> None:
    """Runs a text extraction task async"""
    task = DocumentExtractionTask(document_id, temp_path, mime_type, request_id)
    asyncio.run(task.execute())
