import filetype
from fastapi import UploadFile


def process_upload(uploaded_file: UploadFile):
    pass


def _detect_mime(chunk: bytes):
    mime_type = filetype.guess(chunk)


def _validate_size():
    pass


def _sanitize_filename():
    pass


def _save_to_temp():
    pass


def _delete_from_temp():
    pass
