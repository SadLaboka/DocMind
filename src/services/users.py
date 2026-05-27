
from sqlalchemy.exc import IntegrityError

from src.core.exceptions import ConflictError
from src.core.security import get_password_hash
from src.repositories.users import UserRepository
from src.schemas.users import UserData, UserRegisterRequest, UserRegisterResponse
from src.services.base import BaseService


class UserService(BaseService[UserRepository]):
    """Service for user registration"""
    async def register(self, data: UserRegisterRequest) -> UserRegisterResponse:
        """Register a new user"""
        password_hash = get_password_hash(data.password)

        used_data = UserData(
            login=data.login,
            email=data.email,
            password_hash=password_hash
        )

        try:
            created_user = await self.repository.create_user(used_data)
        except IntegrityError as raw_error:
            if ((hasattr(raw_error.orig, "pgcode") and raw_error.orig.pgcode == "23505") or
                    (hasattr(raw_error.orig, "sqlstate") and raw_error.orig.sqlstate == "23505")):
                raise ConflictError(
                    error_code="user_already_exists",
                    message="Username or email already exists",
                    log_context = {
                        "username": data.login,
                        "email": data.email,
                        "library_hint": str(raw_error)
                    }
                )
            raise

        return UserRegisterResponse.model_validate(created_user)
