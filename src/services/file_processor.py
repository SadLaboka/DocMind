import string
from uuid import uuid4

import filetype
from fastapi import UploadFile

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


def process_upload(uploaded_file: UploadFile):
    pass


def _detect_mime(chunk: bytes):
    return filetype.guess(chunk)


def _validate_size():
    pass


def _get_temp_filename(extension: str) -> str:
    return uuid4().hex + extension


def _sanitize_filename(filename: str) -> str:
    sanitized_filename = "".join(char for char in filename[:200] if char in PERMITTED_CHARS)

    if not sanitized_filename:
        sanitized_filename = "uploaded_file"

    return (
        sanitized_filename
        if sanitized_filename.upper() not in RESERVED_NAMES
        else "_" + sanitized_filename
    )


def _save_to_temp():
    pass


def remove_from_temp():
    pass
