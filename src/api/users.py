from fastapi.routing import APIRouter
from starlette import status

from src.schemas.users import UserRegisterResponse, UserRegisterRequest

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    path="/register",
    summary="Register a new user",
    response_model=UserRegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(user: UserRegisterRequest) -> UserRegisterResponse:
    pass
