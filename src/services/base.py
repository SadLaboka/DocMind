from typing import Generic, TypeVar

from src.repositories.base import BaseRepository

T = TypeVar('T', bound=BaseRepository)


class BaseService(Generic[T]):
    def __init__(self, repository: T):
        self.repository = repository
