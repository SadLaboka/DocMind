import datetime
from beanie import Document, Indexed
from pydantic import Field


class MongoDocument(Document):
    document_id: Indexed(int, unique=True)
    raw_text: str | None = None
    analysis: dict | None = None
    analysis_version: str | None = None
    created_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC))
    updated_at: datetime.datetime = Field(default_factory=lambda: datetime.datetime.now(datetime.UTC))

    class Settings:
        name = "document_contents"
