from fastapi import APIRouter, Depends

from src.DependencyInjection.auth import get_auth_service
from src.services.auth import AuthService
from src.DependencyInjection.auth import get_jwt_manager
from src.core.jwt import JWTManager
from src.schemas.auth import TokenResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
        data: LoginRequest,
        jwt_manager: JWTManager = Depends(get_jwt_manager),
        auth_service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    user = await auth_service.authenticate(username=data.login, password=data.password)

    access_token = jwt_manager.create_access_token(
        {"sub": user.id, "login": data.login, "is_admin": user.is_admin}
    )
    refresh_token = jwt_manager.create_refresh_token({"sub": user.id})
    response = TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")
    return response
