from typing import TypeVar

from src.repositories.base import BaseRepository

T = TypeVar("T", bound=BaseRepository)


class BaseService[T]:
    def __init__(self, repository: T):
        self.repository = repository
