from datetime import datetime

from beanie import Document, Indexed
from pydantic import Field


class MongoDocument(Document):
    document_id: Indexed(int, unique=True)
    raw_text: str | None = None
    analysis: dict | None = None
    analysis_version: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "document_contents"
