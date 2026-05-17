from fastapi.routing import APIRouter
from fastapi import Depends
from starlette import status

from DependencyInjection.users import get_user_service
from src.services.users import UserService
from src.schemas.users import UserRegisterResponse, UserRegisterRequest

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
    pass
