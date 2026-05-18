from DependencyInjection.users import get_user_service
from fastapi import Depends
from fastapi.routing import APIRouter
from starlette import status

from src.schemas.users import UserRegisterRequest, UserRegisterResponse
from src.services.users import UserService

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    path="/register",
    summary="Register a new user",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
        user: UserRegisterRequest,
        service: UserService = Depends(get_user_service)) -> UserRegisterResponse:
    response = await service.register(user)
    return response
