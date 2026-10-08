import asyncio
import time

import structlog

from src.core.database import celery_session_factory
from src.core.enums import DocumentStatus, LLMProvider, MimeType
from src.core.exceptions import ExtractionError
from src.core.mongo_database import init_mongo_for_worker
from src.events.publisher import publish_document_analysis_requested
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.services.analysis import AnalysisService
from src.services.extractors import TextExtractor
from src.storage.exceptions import S3FileNotFoundError, StorageError
from src.storage.s3_storage import get_storage
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

            document = await repo.get_document_by_id(self.document_id)

            if not document:

                self._cleanup_file()

                self.logger.info(
                    "document_not_found",
                    user_id=self.user_id,
                    document_id=self.document_id,
                )

                return

            document_status = document.document_status

            if document_status in (DocumentStatus.uploaded, DocumentStatus.extracting):

                if not await self._is_temp_document_exists() and not await self._restore_file_from_storage(
                    repo, document.file_key
                ):
                    return

                await repo.update_document_fields(self.document_id, document_status=DocumentStatus.extracting)

                await self._process_extraction(repo, mime_enum, document.file_key)
                return
            elif document_status in (DocumentStatus.cancelled, DocumentStatus.failed, DocumentStatus.infected):

                self.logger.warning(
                    "terminal_document_status. Extraction cancelled",
                    user_id=self.user_id,
                    document_id=self.document_id,
                    mime_type=self.mime_type,
                    document_status=document_status.value,
                )

                self._cleanup_file()
                return
            elif document_status in (DocumentStatus.created, DocumentStatus.scanning, DocumentStatus.uploading):
                self.logger.warning(
                    "wrong_document_status_for_extraction",
                    user_id=self.user_id,
                    document_id=self.document_id,
                    mime_type=self.mime_type,
                    document_status=document_status.value,
                )
                return

            self._cleanup_file()

            await self._dispatch_analysis()

    async def _restore_file_from_storage(self, repo: DocumentRepository, file_key: str | None) -> bool:

        if not file_key:
            raise ExtractionError(
                error_code="file_and_key_is_missing",
                log_context={
                    "event_name": "file_and_key_is_missing",
                    "reason": "local_file_and_s3_key_is_missing",
                    "user_id": self.user_id,
                    "document_id": self.document_id,
                    "file_path": self.temp_path,
                    "mime_type": self.mime_type,
                },
            )

        storage = get_storage()
        self.logger.info(
            "start_downloading_document_from_s3",
            user_id=self.user_id,
            document_id=self.document_id,
            temp_path=self.temp_path,
            mime_type=self.mime_type,
        )
        try:
            await storage.download_file(file_key, self.temp_path)
            return True
        except S3FileNotFoundError as err:
            if not err.retryable:
                self.logger.error(
                    "download_file_non_retryable_error",
                    error_code=err.error_code,
                    error_detail=err.message,
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                )
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.failed,
                    temp_filename=None,
                    error_trace=f"Document file is missing. S3 download Error: {err.message}",
                )
                self._cleanup_file()
                return False
            raise
        except StorageError as err:
            if not err.retryable:
                self.logger.error(
                    "download_file_storage_non_retryable_error",
                    error_code=err.error_code,
                    error_detail=err.message,
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                )
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.failed,
                    temp_filename=None,
                    error_trace=f"S3 Storage Error: {err.message}",
                )
                self._cleanup_file()
                return False
            raise

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

    async def _extract_text(
        self, repo: DocumentRepository, mongo_repo: MongoDocumentRepository, mime_enum: MimeType
    ) -> None:
        """Extract text from document and save raw text"""
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

    async def _process_extraction(self, repo: DocumentRepository, mime_enum: MimeType, file_key: str | None) -> None:
        """Launch extraction logic"""

        mongo_repo = MongoDocumentRepository()

        try:
            await self._extract_text(repo, mongo_repo, mime_enum)

            self._cleanup_file()

            await self._dispatch_analysis()

        except ExtractionError as err:
            if err.error_code == "file_not_found":

                if not await self._restore_file_from_storage(repo, file_key):
                    return

                await self._extract_text(repo, mongo_repo, mime_enum)

                self._cleanup_file()

                await self._dispatch_analysis()

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

    async def _is_temp_document_exists(self) -> bool:
        """Checks whether path exists"""
        if not self.temp_path.exists():
            self.logger.warning(
                "Document file not found",
                error_code="processed_file_not_found",
                file_path=self.temp_path,
                user_id=self.user_id,
                document_id=self.document_id,
            )

            return False
        return True

    async def _dispatch_analysis(self) -> None:
        """Creates analysis and dispatches it to processing queue"""
        analysis_repo = MongoAnalysisRepository()
        analysis_service = AnalysisService(analysis_repo)
        analysis = await analysis_service.get_or_create_analysis(
            self.document_id, self.request_id, LLMProvider(self.provider)
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

    @classmethod
    async def _handle_final_failure(cls, document_id: int, request_id: str, exc: Exception) -> None:
        async with celery_session_factory() as session:
            repo = DocumentRepository(session)
            current_doc = await repo.get_document_by_id(document_id)

            if not current_doc:
                return

            if current_doc.document_status != DocumentStatus.extracted:
                await super()._handle_final_failure(document_id, request_id, exc)
                return

            analysis_repo = MongoAnalysisRepository()
            analysis_service = AnalysisService(analysis_repo)

            await analysis_service.mark_dispatch_failed(document_id, request_id, exc)

            return


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
