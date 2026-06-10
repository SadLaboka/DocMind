import structlog
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError
from src.core.security import get_password_hash
from src.repositories.users import UserRepository
from src.schemas.users import UserData, UserRegisterRequest, UserRegisterResponse
from src.services.base import BaseService

logger = structlog.get_logger(__name__)


class UserService(BaseService[UserRepository]):
    """Service for user registration"""

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
                raise ConflictError(
                    error_code="user_already_exists",
                    message="Username or email already exists",
                    log_context={
                        "event_name": "user_registration_conflict",
                        "username": data.login,
                        "email": data.email,
                        "library_hint": str(raw_error),
                    },
                ) from raw_error
            raise

        logger.info(
            "user_registration_success",
            user_id=created_user.id,
            login=created_user.login,
        )

        return UserRegisterResponse.model_validate(created_user)
