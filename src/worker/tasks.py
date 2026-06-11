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


@celery_app.task(
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
    exclude_exceptions=(ExtractionError, ValueError),
    task_acks_late=True,
)
def extract_text_task(document_id: int, temp_path: str, mime_type: str, request_id: str) -> None:
    """Celery task wrapper that runs async extraction logic"""
    asyncio.run(_async_extract(document_id, temp_path, mime_type, request_id))


async def _async_extract(document_id: int, temp_path: str, mime_type: str, request_id: str) -> None:
    """Async implementation of text extraction"""
    structlog.contextvars.bind_contextvars(request_id=request_id)

    path = Path(temp_path)

    logger.info("task_received_by_worker", document_id=document_id, mime_type=mime_type)

    if not mime_type:
        logger.error("task_invalid_mime", document_id=document_id, reason="empty mime type")
        if path.exists():
            path.unlink(missing_ok=True)
        raise ValueError(f"mime_type is required for document {document_id}")

    try:
        mime_enum = MimeType(mime_type)
    except ValueError:
        logger.error("task_invalid_mime", document_id=document_id, reason="unsupported mime", mime_type=mime_type)
        if path.exists():
            path.unlink(missing_ok=True)
        raise ValueError(f"Unsupported mime type: {mime_type}")

    extractor = TextExtractor()

    async with celery_session_factory() as session:
        repo = DocumentRepository(session)

        try:
            start_time = time.perf_counter()

            text = extractor.extract(path, mime_enum)

            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            await repo.update_document_fields(
                document_id=document_id,
                document_text=text,
                document_status=DocumentStatus.success,
                temp_filename=None,
            )

            logger.info(
                "text_extraction_completed",
                document_id=document_id,
                duration_ms=duration_ms,
                text_length=len(text),
            )

            if path.exists():
                path.unlink(missing_ok=True)

        except ExtractionError as err:
            await repo.update_document_fields(
                document_id=document_id,
                document_status=DocumentStatus.failed,
                error_trace=str(err.log_context),
            )
            logger.error(
                "transient_extraction_error",
                document_id=document_id,
                error_detail=str(err),
                exc_info=True,
            )

            if path.exists():
                path.unlink(missing_ok=True)

        except Exception as err:
            await repo.update_document_fields(
                document_id=document_id, document_status=DocumentStatus.failed, error_trace=str(err)
            )
            logger.error(
                "transient_extraction_error",
                document_id=document_id,
                error_detail=str(err),
                exc_info=True,
            )

            raise err

        finally:
            if path.exists():
                path.unlink(missing_ok=True)
