from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.enums import MimeType
from src.models.documents import DocumentStatus


class DocumentBase(BaseModel):
    user_id: int
    filename: str = Field(min_length=5, max_length=255)
    description: str | None = Field(max_length=300, default=None)
    mime_type: MimeType
    file_size: int


class DocumentCreatedResponse(DocumentBase):
    pass


class DocumentResponse(DocumentBase):
    id: int
    status: DocumentStatus
    document_text: str | None
    analysis: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentData(DocumentBase):
    temp_filename: str


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    limit: int
    has_next: bool
