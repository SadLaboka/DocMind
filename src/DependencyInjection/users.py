from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.core.user_active_cache import UserActiveStatusCache, get_user_active_cache
from src.repositories.users import UserRepository
from src.services.users import UserService


def get_user_repository(session: AsyncSession = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def get_user_service(
    repository: UserRepository = Depends(get_user_repository),
    user_active_cache: UserActiveStatusCache = Depends(get_user_active_cache),
) -> UserService:
    return UserService(repository, user_active_cache)
