from typing import TypeVar

from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.base import BaseRepository

T = TypeVar("T", bound=BaseRepository)


class BaseService[T]:
    def __init__(self, repository: T, mongo_repository: MongoDocumentRepository):
        self.repository = repository
        self.mongo_repository = mongo_repository
