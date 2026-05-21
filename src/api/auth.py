from fastapi import APIRouter, Depends

from src.core.jwt import JWTManager
from src.DependencyInjection.auth import get_auth_service, get_jwt_manager
from src.schemas.auth import LoginRequest, TokenResponse
from src.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
        data: LoginRequest,
        jwt_manager: JWTManager = Depends(get_jwt_manager),
        auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    user = await auth_service.authenticate(username=data.login, password=data.password)

    response = TokenResponse(**jwt_manager.get_tokens(
        {"sub": user.id,
         "login": user.login,
         "is_admin": user.is_admin}))
    return response
