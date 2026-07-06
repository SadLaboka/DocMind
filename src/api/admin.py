from fastapi import APIRouter, Depends
from starlette import status

from src.DependencyInjection.auth import get_current_admin_user
from src.DependencyInjection.users import get_user_service
from src.schemas.users import User, UserStatusUpdateRequest, UserWithStatus
from src.services.users import UserService

router = APIRouter(prefix="/admin", tags=["admin"])


@router.patch(
    "/users/{id}/status", summary="Update user status", status_code=status.HTTP_200_OK, response_model=UserWithStatus
)
async def update_user_status(
    id: int,
    data: UserStatusUpdateRequest,
    user_service: UserService = Depends(get_user_service),
    admin_user: User = Depends(get_current_admin_user),
) -> UserWithStatus:

    return await user_service.update_user_active_status(id, data.is_active, admin_user.id)
