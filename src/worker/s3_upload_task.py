import asyncio

import structlog

from src.core.database import celery_session_factory
from src.core.enums import DocumentStatus
from src.repositories.documents import DocumentRepository
from src.storage.exceptions import (
    S3ConnectionError,
    S3UploadError,
    StorageConfigError,
    StorageError,
)
from src.storage.s3_storage import get_storage
from src.worker.base_task import BaseTask
from src.worker.celery_app import app as celery_app
from src.worker.extraction_tasks import extract_text_task


class UploadTask(BaseTask):
    def __init__(
        self,
        document_id: int,
        temp_path: str,
        mime_type: str,
        user_id: int,
        request_id: str,
        provider: str,
    ) -> None:
        super().__init__(
            document_id=document_id,
            temp_path=temp_path,
            mime_type=mime_type,
            user_id=user_id,
            request_id=request_id,
            provider=provider,
        )
        self.storage = get_storage()

    async def execute(self) -> None:
        """Upload task manager"""
        structlog.contextvars.bind_contextvars(request_id=self.request_id)
        self.logger.info(
            "task_received_by_upload_worker",
            user_id=self.user_id,
            document_id=self.document_id,
        )

        async with celery_session_factory() as session:
            repo = DocumentRepository(session)

            if await self._is_document_cancelled(repo):
                return

            if not await self._is_path_exists(repo):
                return

            file_key = self._generate_file_key(self.temp_path.name)
            await repo.update_document_fields(
                document_id=self.document_id,
                document_status=DocumentStatus.uploading,
            )

            try:
                await self._upload_document(file_key)
                await repo.update_document_fields(
                    document_id=self.document_id,
                    file_key=file_key,
                    document_status=DocumentStatus.uploaded,
                )
            except StorageConfigError as e:
                self.logger.error(
                    "upload_config_error",
                    error_code="storage_config_error",
                    error_detail=str(e),
                    document_id=self.document_id,
                    user_id=self.user_id,
                )
                await repo.update_document_fields(
                    document_id=self.document_id,
                    document_status=DocumentStatus.failed,
                    temp_filename=None,
                    error_trace="Storage configuration error",
                )
                self._cleanup_file()
                return

            except S3UploadError as e:
                if not e.retryable:
                    self.logger.error(
                        "upload_non_retryable_error",
                        error_code=e.error_code,
                        error_detail=e.message,
                        document_id=self.document_id,
                        user_id=self.user_id,
                        file_key=file_key,
                    )
                    await repo.update_document_fields(
                        document_id=self.document_id,
                        document_status=DocumentStatus.failed,
                        temp_filename=None,
                        error_trace=f"S3 Upload Error: {e.message}",
                    )
                    self._cleanup_file()
                    return

                self.logger.warning(
                    "upload_retryable_error",
                    error_code=e.error_code,
                    error_detail=e.message,
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                )
                raise

            except S3ConnectionError as e:
                self.logger.warning(
                    "upload_connection_error_retrying",
                    error_code=e.error_code,
                    error_detail=e.message,
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                )
                raise

            except StorageError as e:
                self.logger.error(
                    "upload_storage_error",
                    error_code=e.error_code,
                    error_detail=e.message,
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                )
                raise

            except Exception as e:
                self.logger.error(
                    "upload_unexpected_error",
                    error_code="unexpected_upload_error",
                    error_detail=str(e),
                    document_id=self.document_id,
                    user_id=self.user_id,
                    file_key=file_key,
                    exc_info=True,
                )
                raise

            self.logger.info(
                "document_successfully_uploaded",
                user_id=self.user_id,
                document_id=self.document_id,
                file_key=file_key,
            )
            await self._publish_to_extract()

    async def _upload_document(self, file_key: str) -> None:
        """Initiate document uploading to the s3 storage"""
        self.logger.info(
            "start_upload_document_to_storage",
            user_id=self.user_id,
            document_id=self.document_id,
            file_key=file_key,
        )
        if not await self.storage.file_exists(file_key):
            await self.storage.upload_file(self.temp_path, file_key)

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

    @staticmethod
    def _generate_file_key(name: str) -> str:
        """Creates a unique file key for s3 storage"""
        return f"documents/{name}"


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    exclude_exceptions=(FileNotFoundError, ValueError, StorageConfigError),
    task_acks_late=True,
    on_failure=UploadTask._on_task_failure,
)
def upload_document_task(
    document_id: int,
    temp_path: str,
    mime_type: str,
    user_id: int,
    request_id: str,
    provider: str,
) -> None:
    """Runs task for upload document to the s3 storage"""
    task = UploadTask(
        document_id=document_id,
        temp_path=temp_path,
        mime_type=mime_type,
        user_id=user_id,
        request_id=request_id,
        provider=provider,
    )
    asyncio.run(task.execute())
