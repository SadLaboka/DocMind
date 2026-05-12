from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MimeType(Enum):
    txt = "text/plain"
    docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    pdf = "application/pdf"


class DocumentBase(BaseModel):
    pass


class DocumentUpload(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: int
    user_id: int
    filename: str = Field(min_length=5, max_length=255)
    mime_type: MimeType
    status: str | None
    document_text: str | None
    analysis: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
