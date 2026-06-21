from beanie import Indexed

from src.models.mongo_base import BaseDocument


class MongoDocument(BaseDocument):
    document_id: Indexed(int, unique=True)  # type: ignore
    raw_text: str | None = None
    analysis: dict | None = None
    analysis_version: str | None = None

    class Settings:
        name = "document_contents"
