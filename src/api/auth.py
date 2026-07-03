from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.config import settings
from src.core.exceptions import AuthenticationError
from src.core.jwt import JWTManager
from src.DependencyInjection.auth import get_auth_service, get_jwt_manager, get_current_token_payload
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
                "event_name": "refresh_token_missing",
            },
        )
    token: str = credentials.credentials
    user = await auth_service.verify_refresh_token(token, jwt_manager)

    response = TokenResponse(**jwt_manager.get_tokens({"sub": user.id, "login": user.login, "is_admin": user.is_admin}))
    return response


@router.post("/logout")
async def logout(
        payload: dict = Depends(get_current_token_payload),
        auth_service: AuthService = Depends(get_auth_service),
):
    jti = payload["jti"]
    ttl = int(settings.jwt.refresh_timedelta * 24 * 60 * 60)

    await auth_service.logout(jti, ttl)
    return {"detail": "Successfully logged out"}
