from datetime import datetime, UTC

from src.core.security import check_password
from src.core.exceptions import AuthenticationError
from src.repositories.users import UserRepository
from src.schemas.users import User
from src.services.base import BaseService


class AuthService(BaseService[UserRepository]):
    """Service for authentication"""
    async def authenticate(self, username: str, password: str) -> User:
        """Gets a user from the database by login
         and compares the hash of the passed password with the hash from the database"""
        user = await self.repository.get_user_by_username(username)

        if not user or not check_password(password, user.password_hash):
            raise AuthenticationError(
                error_code="invalid_credentials",
                message="Invalid username or password",
                log_context={
                    "username": username,
                    "user_found": user is not None,
                    "checked_at": datetime.now(UTC).isoformat()
                }
            )
        return User.model_validate(user)

    async def load_user_profile(self, user_id: int) -> User:
        """Gets a user from the database by user_id"""
        user = await self.repository.get_user_by_id(user_id)

        if not user:
            raise AuthenticationError(
                error_code="user_not_found",
                message="User not found",
                log_context={
                    "user_id": user_id,
                    "checked_at": datetime.now(UTC).isoformat(),
                }
            )
        return User.model_validate(user)
