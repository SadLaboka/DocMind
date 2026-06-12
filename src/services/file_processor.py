import asyncio
import string
import time
from pathlib import Path
from uuid import uuid4

import filetype
import structlog
from celery.result import AsyncResult
from fastapi import UploadFile

from src.core.config import settings
from src.core.enums import MimeType
from src.core.exceptions import BadRequestError
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
CHUNK_SIZE = 64 * 1024
ALLOWED_MIME_VALUES = {m.value for m in MimeType}


class UploadService(BaseService[DocumentRepository]):

    async def process_upload(
        self, uploaded_file: UploadFile, user_id: int, description: str | None, request_id: str
    ) -> DocumentResponse:
        """An orchestrator that validates the parameters of the received file,
        saves it to the database and disk, and then returns a response in the form of a Paydantic schema."""

        filename = uploaded_file.filename or "unknown"
        logger.info(
            "document_upload_initiated",
            filename=filename,
            user_id=user_id,
        )

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

        file_extension = Path(uploaded_file.filename).suffix.lower()
        filename = Path(uploaded_file.filename).stem
        temp_filename = self._get_temp_filename(file_extension)
        sanitized_filename = self._sanitize_filename(filename)

        detected_mime = self._detect_mime(uploaded_file)
        mime_type: MimeType

        if detected_mime is not None and detected_mime in ALLOWED_MIME_VALUES:
            mime_type = MimeType(detected_mime)
        elif detected_mime is not None:
            raise BadRequestError(
                error_code="mime_type_is_invalid",
                message="The has an invalid type",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "invalid mime type",
                    "user_id": user_id,
                    "mime_type": detected_mime,
                },
            )
        elif detected_mime is None and file_extension == ".txt":
            mime_type = MimeType.txt
        else:
            raise BadRequestError(
                error_code="mime_type_is_invalid",
                message="The has invalid type",
                log_context={
                    "event_name": "document_upload_rejected",
                    "reason": "unknown mime type",
                    "user_id": user_id,
                    "mime_type": detected_mime,
                },
            )

        try:
            start_time = time.perf_counter()
            temp_path = self._save_to_temp(file=uploaded_file, temp_name=temp_filename)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

            logger.info(
                "file_saved_to_disk",
                filename=sanitized_filename,
                file_size=file_size,
                duration_ms=duration_ms,
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

        data = DocumentData(
            filename=sanitized_filename,
            user_id=user_id,  # temp
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            temp_filename=temp_filename,
        )

        document = await self.repository.create_document(data)

        logger.info(
            "document_saved_to_db",
            document_id=document.id,
            status="created",
        )

        celery_task = await self._send_to_queue_for_extraction(
            document_id=document.id,
            temp_path=temp_path,
            mime_type=mime_type.value,
            request_id=request_id,
        )

        logger.info(
            "task_dispatched_to_queue",
            document_id=document.id,
            celery_task_id=celery_task.id,
        )

        return DocumentResponse.model_validate(document)

    @staticmethod
    async def _send_to_queue_for_extraction(
        document_id: int, temp_path: Path, mime_type: str, request_id: str
    ) -> AsyncResult:
        """Adds a text extraction task to the queue and returns the task object"""
        return await asyncio.to_thread(
            extract_text_task.delay,
            document_id=document_id,
            temp_path=str(temp_path),
            mime_type=mime_type,
            request_id=request_id,
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
    def _save_to_temp(file: UploadFile, temp_name: str) -> Path:
        """Saves the uploaded file to the temp folder on disk by chunks"""
        path = Path(settings.base_dir).parent / "temp" / temp_name
        Path(Path(settings.base_dir).parent / "temp").mkdir(exist_ok=True, parents=True)
        try:
            with open(path, "wb") as temp_file:
                while chunk := file.file.read(CHUNK_SIZE):
                    temp_file.write(chunk)
        except OSError as err:
            if path.exists():
                path.unlink(missing_ok=True)
            raise err

        return path
