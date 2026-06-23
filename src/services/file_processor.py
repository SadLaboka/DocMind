import asyncio
import hashlib
import string
import time
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

import filetype
import structlog
from celery.result import AsyncResult
from fastapi import UploadFile
from sqlalchemy.exc import IntegrityError

from src.core.config import settings
from src.core.enums import MimeType, LLMProvider
from src.core.exceptions import BadRequestError
from src.models.documents import Document
from src.repositories.documents import DocumentRepository
from src.schemas.documents import DocumentData, DocumentResponse
from src.services.base import BaseService
from src.worker.tasks import extract_text_task

logger = structlog.get_logger(__name__)

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
        self, uploaded_file: UploadFile,
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
            raise BadRequestError(
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

        document, is_duplicate, needs_extraction = await self._create_document_with_deduplication(
            file_hash=file_hash,
            temp_path=temp_path,
            temp_filename=temp_filename,
            user_id=user_id,
            sanitized_filename=sanitized_filename,
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            provider=provider,
        )

        logger.info(
            "document_saved_to_db",
            document_id=document.id,
            status=document.document_status.value,
            user_id=user_id,
            is_duplicate=is_duplicate,
            needs_extraction=needs_extraction,
        )

        if needs_extraction:
            celery_task = await self._send_to_queue_for_extraction(
                document_id=document.id,
                temp_path=temp_path,
                user_id=user_id,
                mime_type=mime_type.value,
                request_id=request_id,
                provider=provider.value,
            )
            logger.info("task_dispatched_to_queue", document_id=document.id, celery_task_id=celery_task.id)

        return DocumentResponse.model_validate(document)

    async def _create_duplicate_document(
        self,
        existing_doc: Document,
        user_id: int,
        sanitized_filename: str,
        mime_type: MimeType,
        description: str | None,
        file_size: int,
        temp_path: Path,
        provider: LLMProvider,
    ) -> tuple[Document, bool]:
        """Creates a duplicate document from the existing document-data and
        Returns: (document, content_was_copied)
        """
        data = DocumentData(
            filename=sanitized_filename,
            user_id=user_id,
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            temp_filename=existing_doc.temp_filename,
            file_hash=existing_doc.file_hash,
            document_status=existing_doc.document_status,
            provider=provider,
        )

        document = await self.repository.create_document(data)

        if self.mongo_repository is None:
            logger.error("mongo_repository_not_available", document_id=document.id)
            return document, False

        content_was_copied = False
        try:
            new_doc = await self.mongo_repository.create_duplicate_content(existing_doc.id, document.id)
            if new_doc:
                content_was_copied = True
                self._remove_from_temp(temp_path)
            else:
                # Content was not found in mongo. Don't remove temp_path for extraction in future
                logger.warning(
                    "duplicate_content_not_found_in_mongo",
                    existing_document_id=existing_doc.id,
                    new_document_id=document.id,
                    user_id=user_id,
                    reason="original_content_missing",
                )

                try:
                    await self.mongo_repository.create_content(document.id)
                except Exception as mongo_err:
                    logger.error(
                        "mongo_create_empty_error",
                        document_id=document.id,
                        user_id=user_id,
                        error=str(mongo_err),
                    )

        except Exception as err:
            # Mongo connection error. Don't remove temp_path for extraction
            logger.error(
                "mongo_connection_error",
                document_id=document.id,
                user_id=user_id,
                error=str(err),
            )

            try:
                await self.mongo_repository.create_content(document.id)
            except Exception as mongo_err:
                logger.error(
                    "mongo_create_empty_error",
                    document_id=document.id,
                    user_id=user_id,
                    error=str(mongo_err),
                )

        return document, content_was_copied

    async def _create_document_with_deduplication(
        self,
        file_hash: str,
        temp_path: Path,
        temp_filename: str,
        user_id: int,
        sanitized_filename: str,
        mime_type: MimeType,
        description: str | None,
        file_size: int,
        provider: LLMProvider,
    ) -> tuple[Document, bool, bool]:
        """
        Creates document or returns existing duplicate
        Returns: (document, is_duplicate, needs_extraction)

        needs_extraction is True if this is a new document or this is a duplicate without content in mongo
        """
        existing_doc = await self.repository.get_document_by_hash_and_active_status_and_provider(file_hash, provider)
        if existing_doc:
            logger.info(
                "document_duplicate_found",
                filename=sanitized_filename,
                file_hash=file_hash[:16],
                existing_document_id=existing_doc.id,
                original_status=existing_doc.document_status,
            )
            doc, content_was_copied = await self._create_duplicate_document(
                existing_doc=existing_doc,
                user_id=user_id,
                sanitized_filename=sanitized_filename,
                mime_type=mime_type,
                description=description,
                file_size=file_size,
                temp_path=temp_path,
                provider=provider,
            )
            needs_extraction = not content_was_copied
            return doc, True, needs_extraction

        data = DocumentData(
            filename=sanitized_filename,
            user_id=user_id,
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            temp_filename=temp_filename,
            file_hash=file_hash,
            provider=provider,
        )

        try:
            doc = await self.repository.create_document(data)
            return doc, False, True
        except IntegrityError as err:
            existing_doc = await self.repository.get_document_by_hash_and_active_status_and_provider(
                file_hash,
                provider
            )
            if existing_doc:
                logger.info(
                    "document_found_after_race",
                    filename=sanitized_filename,
                    file_hash=file_hash[:16],
                    user_id=user_id,
                    existing_document_id=existing_doc.id,
                    original_status=existing_doc.document_status,
                )
                doc, content_was_copied = await self._create_duplicate_document(
                    existing_doc=existing_doc,
                    user_id=user_id,
                    sanitized_filename=sanitized_filename,
                    mime_type=mime_type,
                    description=description,
                    file_size=file_size,
                    temp_path=temp_path,
                    provider=provider,
                )
                needs_extraction = not content_was_copied
                return doc, True, needs_extraction

            raise BadRequestError(
                error_code="storage_error",
                message="Failed to save document due to concurrent upload",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "concurrent upload conflict",
                    "user_id": user_id,
                    "file_hash": file_hash[:16],
                },
            ) from err

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

    @staticmethod
    def _remove_from_temp(path: Path) -> None:
        """Removes the uploaded file from the temp folder"""
        if path.exists():
            path.unlink(missing_ok=True)
