from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.core.exceptions import AuthenticationError, ForbiddenError
from src.core.jwt import JWTManager
from src.core.token_blacklist import TokenBlackList, get_token_blacklist
from src.core.user_active_cache import UserActiveStatusCache, get_user_active_cache
from src.repositories.users import UserRepository
from src.schemas.users import User
from src.services.auth import AuthService

http_bearer = HTTPBearer(auto_error=False)


def get_jwt_manager() -> JWTManager:
    return JWTManager()


def get_user_repository(session: AsyncSession = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def get_auth_service(
    repository: UserRepository = Depends(get_user_repository),
    token_blacklist: TokenBlackList = Depends(get_token_blacklist),
    user_active_cache: UserActiveStatusCache = Depends(get_user_active_cache),
) -> AuthService:
    return AuthService(repository, token_blacklist, user_active_cache)


def get_current_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
    jwt_manager: JWTManager = Depends(get_jwt_manager),
) -> dict:
    """Returns the full JWT payload: jti, exp, sub, login, is_admin"""
    if credentials is None:
        raise AuthenticationError(
            error_code="invalid_credentials",
            message="No credentials provided",
            log_context={"event_name": "no_credentials"},
        )
    token = credentials.credentials
    return jwt_manager.get_payload_from_access_token(token)


async def get_current_user(
    payload: dict = Depends(get_current_token_payload),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    if not payload.get("sub") and not payload.get("jti"):
        raise AuthenticationError(
            error_code="invalid_token_payload",
            message="Invalid token payload",
            log_context={
                "event_name": "invalid_token_payload",
                "jti": payload.get("jti"),
                "user_id": payload.get("sub"),
            },
        )
    return await auth_service.get_current_user_from_token_payload(payload)


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise ForbiddenError(
            error_code="user_is_not_admin",
            message="You are not admin",
            log_context={
                "event_name": "user_is_not_admin",
                "user_id": current_user.id,
            },
        )

    return current_user
