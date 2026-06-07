from pathlib import Path

import asyncio
import structlog

from src.worker.celery_app import app as celery_app
from src.services.extractors import TextExtractor
from src.repositories.documents import DocumentRepository
from src.models.documents import DocumentStatus, MimeType
from src.core.database import get_session
from src.core.exceptions import ExtractionError

logger = structlog.get_logger(__name__)


@celery_app.task
def extract_text_task(document_id: int, temp_path: str, mime_type: str) -> None:
    """Celery task wrapper that runs async extraction logic"""
    asyncio.run(_async_extract(document_id, temp_path, mime_type))


async def _async_extract(document_id: int, temp_path: str, mime_type: str) -> None:
    """Async implementation of text extraction"""
    path = Path(temp_path)

    if not mime_type:
        logger.error(f"Task received empty mime_type for document {document_id}")
        if path.exists():
            path.unlink(missing_ok=True)
        raise ValueError(f"mime_type is required for document {document_id}")

    try:
        mime_enum = MimeType(mime_type)
    except ValueError:
        logger.error(f"Unknown mime type '{mime_type}' for document {document_id}")
        if path.exists():
            path.unlink(missing_ok=True)
        raise ValueError(f"Unsupported mime type: {mime_type}")

    extractor = TextExtractor()

    async for session in get_session():
        repo = DocumentRepository(session)

        try:
            text = extractor.extract(path, mime_enum)
            await repo.update_document_fields(
                document_id=document_id,
                document_text=text,
                document_status=DocumentStatus.success,
                temp_filename=None,
            )
            logger.info(f"Successfully extracted text for document {document_id}")

        except ExtractionError as err:
            await repo.update_document_fields(
                document_id=document_id,
                document_status=DocumentStatus.failed,
                error_trace=str(err.log_context),
            )
            logger.error(f"Extraction failed for document {document_id}: {err.log_context}")

        finally:
            if path.exists():
                path.unlink(missing_ok=True)
