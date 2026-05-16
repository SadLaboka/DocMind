from enum import Enum


class MimeType(Enum):
    txt = "text/plain"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    pdf = "application/pdf"


class DocumentStatus(Enum):
    created = "created"
    queued = "queued"
    processing = "processing"
    success = "success"
    failed = "failed"
    cancelled = "cancelled"
