import asyncio
from collections.abc import Callable, Coroutine
import hashlib
import string
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import BinaryIO, Final, Any
from uuid import uuid4

import filetype
import structlog
from celery.result import AsyncResult
from fastapi import UploadFile
from pymongo.errors import ConnectionFailure

from src.core.config import settings
from src.core.enums import LLMProvider, MimeType, DocumentStatus
from src.core.exceptions import BadRequestError, AppBaseError
from src.events.publisher import publish_document_text_extracted
from src.repositories.documents import DocumentRepository
from src.schemas.documents import DocumentData, DocumentResponse
from src.services.base import BaseService
from src.worker.antivirus_tasks import scan_file_task
from src.worker.extraction_tasks import extract_text_task
from src.worker.s3_upload_task import upload_document_task

logger = structlog.get_logger(__name__)

type ProcessingFunc = Callable[[DocumentResponse, PreparedUpload, str, Path, str], Coroutine[Any, Any, DocumentResponse]]

ALPHABET_RU = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
ALPHABET_RU_UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
PERMITTED_CHARS = set(string.ascii_letters + string.digits + "._-" + ALPHABET_RU + ALPHABET_RU_UPPER)
RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "COM10",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
    "LPT10",
}
ALLOWED_MIME_VALUES = {m.value for m in MimeType}


class ProcessingPath(Enum):
    """Processing options when loading a document"""
    FULL_PIPELINE = "full_pipeline"
    EXTRACTION_ONLY = "extraction_only"
    ANALYSIS_ONLY = "analysis_only"


@dataclass(frozen=True, slots=True)
class PreparedUpload:
    """Prepared data for upload process"""
    path: ProcessingPath
    source_document_id: int | None = None
    file_key: str | None = None
    raw_text: str | None = None


class HashingFileSaver:
    """Context manager for saving an uploaded file to disk while calculating its hash"""

    CHUNK_SIZE = 64 * 1024

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._hasher = hashlib.sha256()
        self._file: BinaryIO | None = None
        self._cached_hash: str | None = None

    def __enter__(self) -> "HashingFileSaver":
        """Opens the file for binary writing upon entering the 'with' block"""
        self._file = open(self._file_path, "wb")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Guarantees the file is closed when exiting the 'with' block"""
        if self._file is not None:
            self._file.close()
            self._cached_hash = self._hasher.hexdigest()

    def save_from_stream(self, stream: BinaryIO) -> None:
        """Reads from the input stream in chunks, writes to file, and updates hash"""
        if self._file is None:
            raise RuntimeError("HashingFileSaver is not open. Use 'with' statement")

        while chunk := stream.read(self.CHUNK_SIZE):
            self._hasher.update(chunk)
            self._file.write(chunk)

    def get_hash(self) -> str:
        """Returns the final SHA-256 hex digest of the written data"""
        if self._cached_hash is None:
            raise RuntimeError("HashingFileSaver is closed or not opened")
        return self._cached_hash


class UploadService(BaseService[DocumentRepository]):

    async def process_upload(
        self,
        uploaded_file: UploadFile,
        user_id: int,
        description: str | None,
        request_id: str,
        provider: LLMProvider | None = None,
    ) -> DocumentResponse:
        """Orchestrates file upload: validation, saving, deduplication, and queue dispatch"""

        sanitized_filename, mime_type, file_size, temp_filename = await self._validate_and_prepare_upload(
            uploaded_file=uploaded_file,
            user_id=user_id,
        )

        logger.info("document_upload_initiated", filename=uploaded_file.filename or "unknown", user_id=user_id)

        temp_path = Path(settings.base_dir).parent / "temp" / temp_filename
        Path(Path(settings.base_dir).parent / "temp").mkdir(exist_ok=True, parents=True)

        if provider is None:
            provider = LLMProvider(settings.llm.default_provider)

        document = None

        try:
            try:
                start_time = time.perf_counter()
                with HashingFileSaver(temp_path) as saver:
                    saver.save_from_stream(uploaded_file.file)
                file_hash = saver.get_hash()
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

                logger.info(
                    "file_saved_to_disk",
                    filename=sanitized_filename,
                    file_size=file_size,
                    user_id=user_id,
                    duration_ms=duration_ms,
                    file_hash=file_hash[:16],
                )
            except OSError as err:
                raise AppBaseError(
                    error_code="storage_error",
                    message="Failed to save the file to disk",
                    log_context={
                        "event_name": "file_save_failed",
                        "user_id": user_id,
                        "filename": sanitized_filename,
                        "file_size": file_size,
                        "error_detail": str(err),
                    },
                ) from err

            prepared_data = await self._determine_processing_path(file_hash=file_hash, user_id=user_id)

            upload_processor: Final[dict[ProcessingPath, ProcessingFunc]] = {
                ProcessingPath.FULL_PIPELINE: self._full_pipeline_processing,
                ProcessingPath.EXTRACTION_ONLY: self._extracting_only_processing,
                ProcessingPath.ANALYSIS_ONLY: self._analyzing_only_processing,
            }

            db_kwargs = {
                ProcessingPath.FULL_PIPELINE: {
                    "document_status": DocumentStatus.created,
                    "temp_filename": temp_filename,
                    "file_key": None,
                },
                ProcessingPath.EXTRACTION_ONLY: {
                    "document_status": DocumentStatus.uploaded,
                    "temp_filename": temp_filename,
                    "file_key": prepared_data.file_key
                },
                ProcessingPath.ANALYSIS_ONLY: {
                    "document_status": DocumentStatus.extracted,
                    "temp_filename": None,
                    "file_key": prepared_data.file_key
                },
            }

            document = await self._create_document_for_processing(
                user_id=user_id,
                sanitized_filename=sanitized_filename,
                mime_type=mime_type,
                description=description,
                file_size=file_size,
                file_hash=file_hash,
                provider=provider,
                **db_kwargs[prepared_data.path]
            )

            response_data = await upload_processor[prepared_data.path](
                document,
                prepared_data,
                request_id,
                temp_path,
                temp_filename,
            )
        except Exception as err:
            logger.warning(
                "document_processing_failed",
                document_id=document.id if document else None,
                user_id=user_id,
                error_type=type(err).__name__,
            )

            await self._try_mark_document_failed(user_id=user_id, document=document)
            self._remove_from_temp(temp_path)

            raise

        return response_data

    async def _create_document_for_processing(
            self,
            user_id: int,
            sanitized_filename: str,
            mime_type: MimeType,
            description: str | None,
            file_size: int,
            file_hash: str,
            provider: LLMProvider,
            **db_kwargs
    ) -> DocumentResponse:

        logger.info(
            "start_saving_document_to_db",
            user_id=user_id,
        )

        data = DocumentData(
            filename=sanitized_filename,
            user_id=user_id,
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            file_hash=file_hash,
            provider=provider,
            **db_kwargs
        )
        start_time = time.perf_counter()
        doc = await self.repository.create_document(data)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        logger.info(
            "document_saved_to_db",
            document_id=doc.id,
            status=doc.document_status.value,
            user_id=user_id,
            duration_ms=duration_ms,
        )

        return DocumentResponse.model_validate(doc)


    async def _determine_processing_path(self, file_hash: str, user_id: int) -> PreparedUpload:
        """Determines which document processing path is needed"""

        logger.info(
            "try_to_find_document_duplicates",
            user_id=user_id,
            file_hash=file_hash[:16],
        )
        candidates = await self.repository.get_reuse_candidates(file_hash)

        if candidates:

            candidates_ids = [candidate.id for candidate in candidates]

            try:
                content = await self.mongo_repository.get_content_for_deduplicate(candidates_ids)

                if content:
                    logger.info(
                        "duplicate_found",
                        user_id=user_id,
                        file_hash=file_hash[:16],
                        chosen_path=ProcessingPath.ANALYSIS_ONLY.value,
                    )
                    document = next((doc for doc in candidates if doc.id == content.document_id), None)

                    if document:
                        return PreparedUpload(
                        path=ProcessingPath.ANALYSIS_ONLY,
                        source_document_id=document.id,
                        file_key=document.file_key,
                        raw_text=content.raw_text,
                        )

            except ConnectionFailure as err:
                logger.warning(
                    "raw_text_deduplication_skipped",
                    user_id=user_id,
                    file_hash=file_hash[:16],
                    reason="mongo_error",
                    error_type=type(err).__name__
                )

            logger.info(
                "duplicate_found_without_extracted_text",
                user_id=user_id,
                file_hash=file_hash[:16],
                chosen_path=ProcessingPath.EXTRACTION_ONLY.value,
            )
            return PreparedUpload(
                path=ProcessingPath.EXTRACTION_ONLY,
                source_document_id=candidates[0].id,
                file_key=candidates[0].file_key,
                raw_text=None
            )

        logger.info(
            "duplicates_not_found",
            user_id=user_id,
            file_hash=file_hash[:16],
            chosen_path=ProcessingPath.FULL_PIPELINE.value,
        )
        return PreparedUpload(
            path=ProcessingPath.FULL_PIPELINE,
            source_document_id=None,
            file_key=None,
            raw_text=None
        )

    async def _full_pipeline_processing(
            self,
            document: DocumentResponse,
            prepared_upload: PreparedUpload,
            request_id: str,
            temp_path: Path,
            temp_filename: str,
    ) -> DocumentResponse:
        """
        Publishing a task for full document processing without deduplication
        """

        logger.info(
            "starting_full_pipeline_processing",
            user_id=document.user_id,
            document=document.id,
        )

        if settings.antivirus.enabled:
            celery_task = await self._send_to_queue_for_scanning(
                document_id=document.id,
                temp_path=temp_path,
                user_id=document.user_id,
                mime_type=document.mime_type.value,
                request_id=request_id,
                provider=document.provider.value,
            )
            logger.info("scan_task_dispatched_to_queue", document_id=document.id, celery_task_id=celery_task.id)
        else:
            celery_task = await self._send_to_queue_for_uploading(
                document_id=document.id,
                temp_path=temp_path,
                user_id=document.user_id,
                mime_type=document.mime_type.value,
                request_id=request_id,
                provider=document.provider.value,
            )
            logger.info("upload_task_dispatched_to_queue", document_id=document.id, celery_task_id=celery_task.id)

        return document

    async def _extracting_only_processing(
            self,
            document: DocumentResponse,
            prepared_upload: PreparedUpload,
            request_id: str,
            temp_path: Path,
            temp_filename: str,
    ) -> DocumentResponse:
        """
        Publishing a task for partial processing with text extraction only
        """
        logger.info(
            "start_extracting_only_processing",
            user_id=document.user_id,
            document=document.id,
        )

        celery_task = await self._send_to_queue_for_extraction(
            document_id=document.id,
            temp_path=temp_path,
            user_id=document.user_id,
            mime_type=document.mime_type.value,
            request_id=request_id,
            provider=document.provider.value,
        )
        logger.info("extract_task_dispatched_to_queue", document_id=document.id, celery_task_id=celery_task.id)

        return document

    async def _analyzing_only_processing(
            self,
            document: DocumentResponse,
            prepared_upload: PreparedUpload,
            request_id: str,
            temp_path: Path,
            temp_filename: str,
    ) -> DocumentResponse:
        """
        Full deduplication processing. Publishes an event for document analysis or degrades to partial processing
        """

        logger.info(
            "start_analyzing_only_processing",
            user_id=document.user_id,
            document_id=document.id,
        )

        if not prepared_upload.raw_text:
            raise ValueError("raw_text is missing or empty in analysis-only processing path")

        try:
            await self.mongo_repository.upsert_raw_text(document_id=document.id, raw_text=prepared_upload.raw_text)
        except ConnectionFailure:
            logger.warning(
                "processing_path_degradated_to_extraction_only",
                user_id=document.user_id,
            )

            document = await self.repository.update_document_fields(
                document_id=document.id,
                document_status=DocumentStatus.uploaded,
                temp_filename=temp_filename,
            )

            document = DocumentResponse.model_validate(document)

            return await self._extracting_only_processing(
                document=document,
                prepared_upload=prepared_upload,
                request_id=request_id,
                temp_path=temp_path,
                temp_filename=temp_filename,
            )

        self._remove_from_temp(temp_path)

        await self._publish_to_analysis(
            document_id=document.id,
            user_id=document.user_id,
            mime_type=document.mime_type.value,
            request_id=request_id,
            provider=document.provider.value,
        )

        logger.info(
            "document_text_extracted_event_published",
            document_id=document.id,
            user_id=document.user_id,
        )

        return document

    async def _validate_and_prepare_upload(
        self, uploaded_file: UploadFile, user_id: int
    ) -> tuple[str, MimeType, int, str]:
        """
        Validates uploaded file and returns prepared metadata
        Returns: (sanitized_filename, mime_type, file_size, temp_filename)
        """
        if not uploaded_file.filename:
            raise BadRequestError(
                error_code="filename_is_missing",
                message="The uploaded file is missing a filename",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "filename missing",
                    "user_id": user_id,
                },
            )

        file_size = self._validate_size(uploaded_file)
        if file_size is None:
            raise BadRequestError(
                error_code="file_size_is_invalid",
                message="The uploaded file is too big",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "file too big",
                    "user_id": user_id,
                    "file_size": file_size,
                },
            )
        elif file_size == 0:
            raise BadRequestError(
                error_code="file_size_is_invalid",
                message="The uploaded file is empty",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "file is empty",
                    "user_id": user_id,
                    "file_size": file_size,
                },
            )

        detected_mime = self._detect_mime(uploaded_file)
        file_extension = Path(uploaded_file.filename).suffix.lower()
        mime_type = self._validate_mime_type(detected_mime, file_extension, user_id)

        temp_filename = self._get_temp_filename(file_extension)
        sanitized_filename = self._sanitize_filename(uploaded_file.filename)

        return sanitized_filename, mime_type, file_size, temp_filename

    @staticmethod
    def _validate_mime_type(detected_mime: str | None, file_extension: str, user_id: int) -> MimeType:
        """Validates and returns MimeType enum"""
        if detected_mime is not None and detected_mime in ALLOWED_MIME_VALUES:
            return MimeType(detected_mime)
        elif detected_mime is not None:
            raise BadRequestError(
                error_code="mime_type_is_invalid",
                message="The file has an invalid type",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "invalid mime type",
                    "user_id": user_id,
                    "mime_type": detected_mime,
                },
            )
        elif detected_mime is None and file_extension == ".txt":
            return MimeType.txt
        else:
            raise BadRequestError(
                error_code="mime_type_is_invalid",
                message="The file has an invalid type",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "unknown mime type",
                    "user_id": user_id,
                    "mime_type": detected_mime,
                },
            )

    @staticmethod
    async def _publish_to_analysis(
            document_id: int, mime_type: str, request_id: str, user_id: int, provider: str
    ) -> None:
        """Publishes document to analysis queue"""
        await asyncio.to_thread(
            publish_document_text_extracted,
            document_id=document_id,
            user_id=user_id,
            mime_type=mime_type,
            request_id=request_id,
            provider=provider,
        )

    @staticmethod
    async def _send_to_queue_for_scanning(
        document_id: int, temp_path: Path, mime_type: str, request_id: str, user_id: int, provider: str
    ) -> AsyncResult:
        """Adds a document scanning task to the queue and returns the task object"""
        return await asyncio.to_thread(
            scan_file_task.delay,
            document_id=document_id,
            temp_path=str(temp_path),
            mime_type=mime_type,
            user_id=user_id,
            request_id=request_id,
            provider=provider,
        )

    @staticmethod
    async def _send_to_queue_for_uploading(
        document_id: int, temp_path: Path, mime_type: str, request_id: str, user_id, provider: str
    ) -> AsyncResult:
        """Adds a document s3-uploading task to the queue and returns the task object"""
        return await asyncio.to_thread(
            upload_document_task.delay,
            document_id=document_id,
            temp_path=str(temp_path),
            mime_type=mime_type,
            user_id=user_id,
            request_id=request_id,
            provider=provider,
        )


    @staticmethod
    async def _send_to_queue_for_extraction(
        document_id: int, temp_path: Path, mime_type: str, request_id: str, user_id: int, provider: str
    ) -> AsyncResult:
        """Adds a text extraction task to the queue and returns the task object"""
        return await asyncio.to_thread(
            extract_text_task.delay,
            document_id=document_id,
            temp_path=str(temp_path),
            mime_type=mime_type,
            user_id=user_id,
            request_id=request_id,
            provider=provider,
        )

    @staticmethod
    def _detect_mime(uploaded_file: UploadFile) -> str | None:
        """Determines the mime type by the magic bytes at the beginning"""
        file_type = filetype.guess(uploaded_file.file.read(2048))
        uploaded_file.file.seek(0)
        return file_type.mime if file_type else None

    @staticmethod
    def _validate_size(uploaded_file: UploadFile) -> int | None:
        """Validates the size of the uploaded file"""
        max_bytes = 1024 * 1024 * 50
        uploaded_file.file.seek(0, 2)
        file_size = uploaded_file.file.tell()
        uploaded_file.file.seek(0)

        if file_size > max_bytes:
            return None

        return file_size

    @staticmethod
    def _get_temp_filename(extension: str) -> str:
        """Generates a temporary filename"""
        return uuid4().hex + extension

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Converts a file name to a safe form"""
        filename = filename.replace(" ", "_")
        sanitized_filename = "".join(char for char in filename[:200] if char in PERMITTED_CHARS)

        if not sanitized_filename:
            sanitized_filename = "uploaded_file"

        return sanitized_filename if sanitized_filename.upper() not in RESERVED_NAMES else "_" + sanitized_filename

    async def _try_mark_document_failed(self, user_id: int, document: DocumentResponse | None) -> None:
        """Tries to change the document status to failed"""
        if document:
            try:
                logger.info(
                    "trying_change_document_status_to_failed",
                    user_id=user_id,
                    document_id=document.id,
                )

                await self.repository.update_document_fields(
                    document_id=document.id,
                    temp_filename=None,
                    document_status=DocumentStatus.failed,
                    error_trace="Document processing failed",
                )
                logger.info(
                    "document_status_changed_to_failed",
                    user_id=user_id,
                    document_id=document.id,
                )
            except Exception as err:
                logger.warning(
                    "document_status_was_not_changed_to_failed",
                    user_id=user_id,
                    document_id=document.id,
                    error_type=type(err).__name__,
                )
            return

    @staticmethod
    def _remove_from_temp(path: Path) -> None:
        """Removes the uploaded file from the temp folder"""
        try:
            if path.exists():
                path.unlink(missing_ok=True)
        except OSError as err:
            logger.warning(
                "temp_file_removing_failed",
                path=str(path),
                err=str(err),
            )
