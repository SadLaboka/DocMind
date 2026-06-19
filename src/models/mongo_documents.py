import datetime

from beanie import Document, Indexed
from pydantic import Field


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class MongoDocument(Document):
    document_id: Indexed(int, unique=True)  # type: ignore
    raw_text: str | None = None
    analysis: dict | None = None
    analysis_version: str | None = None
    created_at: datetime.datetime = Field(default_factory=_utc_now)
    updated_at: datetime.datetime = Field(default_factory=_utc_now)

    class Settings:
        name = "document_contents"
