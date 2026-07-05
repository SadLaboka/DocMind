from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.user_active_cache import UserActiveStatusCache, get_user_active_cache
from src.core.database import get_session
from src.core.exceptions import AuthenticationError
from src.core.jwt import JWTManager
from src.core.token_blacklist import TokenBlackList, get_token_blacklist
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
    payload: dict = Depends(get_current_token_payload), token_blacklist: TokenBlackList = Depends(get_token_blacklist)
) -> User:
    jti = payload.get("jti")
    if jti and await token_blacklist.is_blacklisted(jti):
        raise AuthenticationError(
            error_code="token_revoked",
            message="Token has been revoked",
            log_context={
                "event_name": "token_blacklisted",
                "jti": jti,
                "user_id": payload["sub"],
            },
        )

    return User(id=int(payload["sub"]), login=payload["login"], is_admin=payload["is_admin"])
