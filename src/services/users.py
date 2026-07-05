import structlog
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError, BadRequestError, ResourceNotFoundError
from src.core.security import get_password_hash
from src.core.user_active_cache import UserActiveStatusCache
from src.repositories.users import UserRepository
from src.schemas.users import UserData, UserRegisterRequest, UserRegisterResponse, UserWithStatus
from src.services.base import BaseService

logger = structlog.get_logger(__name__)


class UserService(BaseService[UserRepository]):
    """Service for user registration"""
    def __init__(self, repository: UserRepository, user_active_cache: UserActiveStatusCache):
        super().__init__(repository)
        self.user_active_cache = user_active_cache

    async def register(self, data: UserRegisterRequest) -> UserRegisterResponse:
        """Register a new user"""
        logger.info(
            "user_registration_initiated",
            login=data.login,
            email=data.email,
        )

        password_hash = get_password_hash(data.password)

        used_data = UserData(login=data.login, email=data.email, password_hash=password_hash)

        try:
            created_user = await self.repository.create_user(used_data)
        except IntegrityError as raw_error:
            orig = raw_error.orig
            if orig is not None and (
                getattr(orig, "pgcode", None) == "23505" or getattr(orig, "sqlstate", None) == "23505"
            ):
                pgcode = getattr(orig, "pgcode", "unknown")
                constraint_name = getattr(orig, "constraint_name", "unknown")

                raise ConflictError(
                    error_code="user_already_exists",
                    message="Username or email already exists",
                    log_context={
                        "event_name": "user_registration_conflict",
                        "username": data.login,
                        "email": data.email,
                        "pgcode": pgcode,
                        "constraint_name": constraint_name,
                    },
                ) from raw_error
            raise

        logger.info(
            "user_registration_success",
            user_id=created_user.id,
            login=created_user.login,
        )

        return UserRegisterResponse.model_validate(created_user)

    async def update_user_active_status(self, user_id: int, is_active: bool, initiator_id: int) -> UserWithStatus:
        """Update the active status of the user"""
        logger.info(
            "user_update_active_status_initiated",
            user_id=user_id,
            initiator_id=initiator_id,
        )

        if user_id == initiator_id:
            raise BadRequestError(
                error_code="cannot_deactivate_yourself",
                message="You cannot deactivate yourself",
                log_context={
                    "event_name": "user_update_active_status_impossible",
                    "user_id": user_id,
                    "initiator_id": initiator_id,
                }
            )

        user = await self.repository.update_is_active(user_id, is_active)

        if not user:
            raise ResourceNotFoundError(
                error_code="user_not_found",
                message="User not found",
                log_context={
                    "event_name": "user_not_found",
                    "user_id": user_id,
                    "initiator_id": initiator_id,
                }
            )

        await self.user_active_cache.set_active(user_id, is_active)

        logger.info(
            "user_status_change",
            is_active=is_active,
            user_id=user_id,
            initiator_id=initiator_id,
        )

        return UserWithStatus.model_validate(user)
