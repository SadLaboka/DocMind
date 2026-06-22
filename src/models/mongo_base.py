import datetime

from beanie import Document
from pydantic import Field


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class BaseDocument(Document):
    created_at: datetime.datetime = Field(default_factory=_utc_now)
    updated_at: datetime.datetime = Field(default_factory=_utc_now)
