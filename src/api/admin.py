from fastapi import APIRouter, Depends
from starlette import status

from src.DependencyInjection.prompts import get_prompt_service
from src.services.prompts import PromptService
from src.schemas.prompts import PromptResponse, PromptRequest
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


@router.post(
    "/prompts",
    summary="Create new prompt",
    status_code=status.HTTP_201_CREATED,
    response_model=PromptResponse
)
async def create_prompt(
        prompt: PromptRequest,
        admin_user: User = Depends(get_current_admin_user),
        prompt_service: PromptService = Depends(get_prompt_service)
) -> PromptResponse:
    prompt_data = await prompt_service.create_prompt(
        version=prompt.version, prompt_type=prompt.prompt_type, content=prompt.content)

    return PromptResponse.model_validate(prompt_data)
