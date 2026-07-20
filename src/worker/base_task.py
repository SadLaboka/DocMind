import asyncio
from pathlib import Path

import structlog

from src.core.database import celery_session_factory
from src.core.enums import DocumentStatus
from src.repositories.documents import DocumentRepository


class BaseTask:
    def __init__(
        self, document_id: int, temp_path: str, mime_type: str, user_id: int, request_id: str, provider: str
    ) -> None:
        self.document_id = document_id
        self.temp_path = Path(temp_path)
        self.mime_type = mime_type
        self.user_id = user_id
        self.request_id = request_id
        self.provider = provider
        self.logger = structlog.get_logger(self.__class__.__name__)

    @classmethod
    def _on_task_failure(cls, exc, task_id, args, kwargs, _einfo) -> None:
        """
        Celery callback for on_failure
        Called after all retries have been exhausted
        Does not delete the tempo file here to allow manual restarts
        """
        document_id = kwargs.get("document_id")
        task_logger = structlog.get_logger(cls.__name__)
        if document_id:
            task_logger.error(
                "task_final_failure",
                document_id=document_id,
                task_id=task_id,
                user_id=kwargs.get("user_id"),
                error_detail=str(exc),
            )
            asyncio.run(cls._update_status_after_failure(document_id, str(exc)))

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

    async def _is_document_cancelled(self, repo: DocumentRepository) -> bool:
        """Checks whether document processing has been canceled"""
        current_doc = await repo.get_document_by_id(self.document_id)
        if not current_doc or current_doc.document_status == DocumentStatus.cancelled:
            self.logger.info("document_cancelled_or_deleted", document_id=self.document_id)
            self._cleanup_file()
            return True
        return False

    def _cleanup_file(self) -> None:
        """Safely cleanup file"""
        if self.temp_path.exists():
            self.temp_path.unlink(missing_ok=True)
