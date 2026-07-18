import asyncio
import structlog

from src.antivirus.exceptions import AntivirusUnavailableError
from src.antivirus.scanner import AntivirusScanner, ScanResult
from src.core.config import settings
from src.core.database import celery_session_factory
from src.core.enums import DocumentStatus
from src.repositories.documents import DocumentRepository
from src.worker.celery_app import app as celery_app
from src.worker.extraction_tasks import extract_text_task
from src.worker.base_task import BaseTask


class DocumentScanTask(BaseTask):
    def __init__(
            self,
            document_id: int,
            temp_path: str,
            mime_type: str,
            user_id: int,
            request_id: str,
            provider: str
    ) -> None:
        super().__init__(
            document_id,
            temp_path,
            mime_type,
            user_id,
            request_id,
            provider
        )
        self.scanner = AntivirusScanner()
        self.fail_on_unavailable = settings.antivirus.fail_on_unavailable

    async def execute(self) -> None:
        """Scanning task manager"""
        structlog.contextvars.bind_contextvars(request_id=self.request_id)
        self.logger.info(
            "task_received_by_antivirus_worker",
            user_id=self.user_id,
            document_id=self.document_id,
            mime_type=self.mime_type
        )

        async with celery_session_factory() as session:
            repo = DocumentRepository(session)

            if await self._is_document_cancelled(repo):
                self.logger.info(
                    "document_status_is_cancelled",
                    user_id=self.user_id,
                    document_id=self.document_id,
                    mime_type=self.mime_type
                )
                return

            if not self.temp_path.exists():
                await repo.update_document_fields(self.document_id, document_status=DocumentStatus.cancelled)
                self.logger.error(
                    "Document not found",
                    error_code="scan_file_not_found",
                    file_path=self.temp_path,
                    user_id=self.user_id,
                    document_id=self.document_id,
                    mime_type=self.mime_type
                )
                return

            await repo.update_document_fields(self.document_id, document_status=DocumentStatus.scanning)

            scan_result = await self._process_scanning()

            if scan_result is None:
                if self.fail_on_unavailable:
                    await repo.update_document_fields(
                        document_id=self.document_id,
                        document_status=DocumentStatus.failed,
                        error_trace="Antivirus service unavailable",
                    )
                    self._cleanup_file()
                else:
                    self.logger.warning(
                        "scan_skipped_antivirus_unavailable",
                        document_id=self.document_id,
                        user_id=self.user_id,
                    )
                    await repo.update_document_fields(
                        document_id=self.document_id,
                        document_status=DocumentStatus.extracting,
                    )
                    await self._publish_to_extract()
                return

            if scan_result:
                if scan_result.is_infected:
                    self.logger.warning(
                        "scan_completed_infected",
                        signature=scan_result.signature,
                        duration=scan_result.duration_ms,
                        document_id=self.document_id,
                        user_id=self.user_id,
                    )
                    await repo.update_document_fields(
                        self.document_id,
                        document_status=DocumentStatus.infected,
                        error_trace=f"Malware detected: {scan_result.signature}",
                    )
                    self._cleanup_file()
                    return
                else:
                    self.logger.info(
                        "scan_completed_clean",
                        duration=scan_result.duration_ms,
                        document_id=self.document_id,
                        user_id=self.user_id,
                    )

                    await repo.update_document_fields(self.document_id, document_status=DocumentStatus.extracting)
                    await self._publish_to_extract()


    async def _publish_to_extract(self) -> None:
        """Publish document to extract text task"""
        await asyncio.to_thread(
            extract_text_task.delay,
            document_id=self.document_id,
            temp_path=str(self.temp_path),
            mime_type=self.mime_type,
            user_id=self.user_id,
            request_id=self.request_id,
            provider=self.provider,
        )

    async def _process_scanning(self) -> ScanResult | None:
        """Launch scanning logic"""
        try:
            self.logger.info(
                "initiate_document_scan",
                user_id=self.user_id,
                file_path=self.temp_path,
                document_id=self.document_id,
                mime_type=self.mime_type
            )
            return self.scanner.scan_file(self.temp_path)

        except AntivirusUnavailableError as err:
            if self.fail_on_unavailable:
                self.logger.error(
                    "antivirus_unavailable",
                    error_code=err.error_code,
                    user_id=self.user_id,
                    document_id=self.document_id,
                    original_error=err.original_error,
                )
            else:
                self.logger.warning(
                    "antivirus_unavailable",
                    error_code=err.error_code,
                    user_id=self.user_id,
                    document_id=self.document_id,
                    original_error=err.original_error,
                )
            return None


@celery_app.task(
    autoretry_for=(),
    exclude_exceptions=(FileNotFoundError, ValueError),
    task_acks_late=True,
    on_failure=DocumentScanTask._on_task_failure,
)
def scan_file_task(
        document_id: int,
        temp_path: str,
        mime_type: str,
        user_id: int,
        request_id: str,
        provider: str,
) -> None:
    """Runs a document scan task async"""
    task = DocumentScanTask(
        document_id=document_id,
        temp_path=temp_path,
        mime_type=mime_type,
        user_id=user_id,
        request_id=request_id,
        provider=provider,
    )
    asyncio.run(task.execute())
