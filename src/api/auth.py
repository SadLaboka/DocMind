from fastapi import APIRouter, Depends

from src.DependencyInjection.auth import get_jwt_manager
from src.core.jwt import JWTManager
from src.schemas.auth import TokenResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
        data: LoginRequest,
        jwt_manager: JWTManager = Depends(get_jwt_manager),
) -> TokenResponse:
    access_token = jwt_manager.create_access_token({"username": data.login})
    refresh_token = jwt_manager.create_refresh_token({"username": data.login})
    response = TokenResponse(access_token=access_token, refresh_token=refresh_token, token_type="bearer")
    return response
