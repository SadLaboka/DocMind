from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.users import User
from src.core.database import get_session
from src.core.jwt import JWTManager
from src.repositories.users import UserRepository
from src.services.auth import AuthService

http_bearer = HTTPBearer(auto_error=False)


def get_jwt_manager():
    return JWTManager()


def get_user_repository(session: AsyncSession = Depends(get_session)) -> UserRepository:
    return UserRepository(session)


def get_auth_service(repository: UserRepository = Depends(get_user_repository)) -> AuthService:
    return AuthService(repository)


def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
        jwt_manager: JWTManager = Depends(get_jwt_manager)
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials")
    token = credentials.credentials
    token_payload = jwt_manager.get_payload_from_access_token(token)
    return User(
        id=int(token_payload["sub"]),
        login=token_payload["login"],
        is_admin=token_payload["is_admin"]
    )
