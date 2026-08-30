import asyncio
from pathlib import Path

import structlog

from src.core.database import celery_session_factory
from src.core.enums import DocumentStatus, AnalysisStatus, AnalysisFailureKind
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_analyses import MongoAnalysisRepository


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
        """
        document_id = kwargs.get("document_id")
        request_id = kwargs.get("request_id")
        temp_path = Path(kwargs.get("temp_path"))
        task_logger = structlog.get_logger(cls.__name__)
        user_id = kwargs.get("user_id")
        if document_id:
            task_logger.error(
                "task_final_failure",
                document_id=document_id,
                task_id=task_id,
                user_id=user_id,
                error_detail=str(exc),
            )
            try:
                asyncio.run(cls._update_status_after_failure(request_id, document_id, exc))
            except Exception as err:
                task_logger.error(
                    "update_status_after_failure_failed",
                    document_id=document_id,
                    task_id=task_id,
                    user_id=user_id,
                    error_detail=str(err),
                )

            try:
                if temp_path.exists():
                    temp_path.unlink(missing_ok=True)

                    task_logger.info("temp_file_successfully_removed")

            except OSError as err:
                task_logger.warning(
                    "temp_file_removing_failed",
                    path=str(temp_path),
                    err=str(err),
                )

    @staticmethod
    async def _update_status_after_failure(request_id: str, document_id: int, exc: Exception) -> None:
        """Updates document status after final failure"""
        async with celery_session_factory() as session:
            repo = DocumentRepository(session)
            current_doc = await repo.get_document_by_id(document_id)

            if not current_doc.document_status == DocumentStatus.extracted:

                if current_doc and current_doc.document_status != DocumentStatus.cancelled:
                    await repo.update_document_fields(
                        document_id=document_id,
                        document_status=DocumentStatus.failed,
                        temp_filename=None,
                        error_trace=f"Task failed after all retries: {str(exc)}",
                    )

                    return

        analysis_repo = MongoAnalysisRepository()

        analysis = await analysis_repo.get_analysis_by_document_and_request(
            document_id=document_id,
            request_id=request_id,
        )

        if not analysis:
            return

        await analysis_repo.update_analysis_fields(
            document_id=document_id,
            request_id=request_id,
            status=AnalysisStatus.failed,
            failure_kind=AnalysisFailureKind.transient,
            error_code=getattr(exc, "error_code", None),
            error_detail=str(exc),
        )
        return


    async def _is_document_cancelled(self, repo: DocumentRepository) -> bool:
        """Checks whether document processing has been canceled"""
        current_doc = await repo.get_document_by_id(self.document_id)
        if not current_doc or current_doc.document_status == DocumentStatus.cancelled:

            self._cleanup_file()

            self.logger.info(
                "document_status_is_cancelled",
                user_id=self.user_id,
                document_id=self.document_id,
            )

            return True
        return False

    async def _is_path_exists(self, repo: DocumentRepository) -> bool:
        """Checks whether path exists"""
        if not self.temp_path.exists():
            await repo.update_document_fields(self.document_id, document_status=DocumentStatus.cancelled)
            self.logger.error(
                "Document not found",
                error_code="processed_file_not_found",
                file_path=self.temp_path,
                user_id=self.user_id,
                document_id=self.document_id,
            )

            return False
        return True

    def _cleanup_file(self) -> None:
        """Safely cleanup file"""
        try:
            if self.temp_path.exists():
                self.temp_path.unlink(missing_ok=True)
        except OSError as err:
            self.logger.warning(
                "temp_file_removing_failed",
                path=str(self.temp_path),
                err=str(err),
            )
