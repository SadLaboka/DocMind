from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.exceptions import AuthenticationError
from src.core.jwt import JWTManager
from src.DependencyInjection.auth import get_auth_service, get_jwt_manager
from src.schemas.auth import LoginRequest, TokenResponse
from src.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

http_bearer = HTTPBearer(auto_error=False)


@router.post("/login", response_model=TokenResponse)
async def login(
    data: LoginRequest,
    jwt_manager: JWTManager = Depends(get_jwt_manager),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    user = await auth_service.authenticate(username=data.login, password=data.password)

    response = TokenResponse(**jwt_manager.get_tokens({"sub": user.id, "login": user.login, "is_admin": user.is_admin}))
    return response


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    jwt_manager: JWTManager = Depends(get_jwt_manager),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    if credentials is None:
        raise AuthenticationError(
            error_code="invalid_credentials",
            message="No credentials provided",
            log_context={
                "message": "Authentication credentials were not provided",
                "checked_at": datetime.now(UTC).isoformat(),
            },
        )
    token: str = credentials.credentials
    user_id = jwt_manager.get_sub_from_refresh_token(token)
    user = await auth_service.load_user_profile(user_id)

    response = TokenResponse(**jwt_manager.get_tokens({"sub": user.id, "login": user.login, "is_admin": user.is_admin}))
    return response
