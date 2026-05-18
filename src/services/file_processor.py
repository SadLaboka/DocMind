import string
from pathlib import Path
from uuid import uuid4

import filetype
from fastapi import HTTPException, UploadFile

from services.base import BaseService
from src.core.config import settings
from src.core.enums import MimeType
from src.schemas.documents import DocumentCreatedResponse, DocumentData

ALPHABET_RU = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя"
ALPHABET_RU_UPPER = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
PERMITTED_CHARS = set(
    string.ascii_letters + string.digits + "._-" + ALPHABET_RU + ALPHABET_RU_UPPER
)
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


    def process_upload(
        self,
        uploaded_file: UploadFile,
        user_id: int, description: str | None
    ) -> DocumentCreatedResponse:
        """An orchestrator that validates the parameters of the received file,
        saves it to the database and disk, and then returns a response in the form of a Paydantic schema."""
        if not uploaded_file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        file_size = self._validate_size(uploaded_file)

        file_extension = Path(uploaded_file.filename).suffix.lower()
        filename = Path(uploaded_file.filename).stem
        temp_filename = self._get_temp_filename(file_extension)
        sanitized_filename = self._sanitize_filename(filename)

        mime_type = self._detect_mime(uploaded_file)
        if mime_type is not None and mime_type in ALLOWED_MIME_VALUES:
            mime_type = MimeType(mime_type)
        elif mime_type is not None:
            raise HTTPException(status_code=415, detail="Wrong file type")
        elif mime_type is None and file_extension == ".txt":
            mime_type = MimeType.txt
        else:
            raise HTTPException(status_code=415, detail="Wrong file type")

        self._save_to_temp(file=uploaded_file, temp_name=temp_filename)

        data = DocumentData(
            filename=sanitized_filename,
            user_id=user_id,  # temp
            mime_type=mime_type,
            description=description,
            file_size=file_size,
            temp_filename=temp_filename,
        )

        # save_to_db(data)

        return DocumentCreatedResponse(
            filename=data.filename,
            user_id=data.user_id,
            mime_type=data.mime_type,
            description=data.description,
            file_size=data.file_size,
        )

    @staticmethod
    def _detect_mime(uploaded_file: UploadFile) -> str | None:
        """Determines the mime type by the magic bytes at the beginning"""
        file_type = filetype.guess(uploaded_file.file.read(64))
        uploaded_file.file.seek(0)
        return file_type.mime if file_type else None

    @staticmethod
    def _validate_size(uploaded_file: UploadFile) -> int:
        """Validates the size of the uploaded file"""
        max_bytes = 1024 * 1024 * 50
        uploaded_file.file.seek(0, 2)
        file_size = uploaded_file.file.tell()
        uploaded_file.file.seek(0)

        if file_size > max_bytes:
            raise HTTPException(status_code=413, detail="File too big")

        return file_size

    @staticmethod
    def _get_temp_filename(extension: str) -> str:
        """Generates a temporary filename"""
        return uuid4().hex + extension

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Converts a file name to a safe form"""
        sanitized_filename = "".join(char for char in filename[:200] if char in PERMITTED_CHARS)

        if not sanitized_filename:
            sanitized_filename = "uploaded_file"

        return (
            sanitized_filename
            if sanitized_filename.upper() not in RESERVED_NAMES
            else "_" + sanitized_filename
        )

    @staticmethod
    def _save_to_temp(file: UploadFile, temp_name: str) -> None:
        """Saves the uploaded file to the temp folder on disk by chunks"""
        path = settings.base_dir / "temp" / temp_name
        Path(settings.base_dir / "temp").mkdir(exist_ok=True, parents=True)
        with open(path, "wb") as temp_file:
            while chunk := file.file.read(CHUNK_SIZE):
                temp_file.write(chunk)
