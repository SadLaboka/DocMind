import structlog

from src.core.exceptions import AuthenticationError
from src.core.security import check_password
from src.repositories.users import UserRepository
from src.schemas.users import User
from src.services.base import BaseService

logger = structlog.get_logger(__name__)


class AuthService(BaseService[UserRepository]):
    """Service for authentication"""

    async def authenticate(self, username: str, password: str) -> User:
        """Gets a user from the database by login
        and compares the hash of the passed password with the hash from the database"""
        logger.info("login_attempt", login=username)

        user = await self.repository.get_user_by_username(username)

        if not user:
            raise AuthenticationError(
                error_code="invalid_credentials",
                message="Invalid username or password",
                log_context={
                    "event_name": "login_failed",
                    "reason": "invalid username",
                    "username": username,
                    "user_found": False,
                },
            )

        if not check_password(password, user.password_hash):
            raise AuthenticationError(
                error_code="invalid_credentials",
                message="Invalid username or password",
                log_context={
                    "event_name": "login_failed",
                    "reason": "invalid password",
                    "username": username,
                    "user_found": True,
                },
            )

        logger.info(
            "login_success",
            user_id=user.id,
            login=user.login,
            is_admin=user.is_admin,
        )

        return User.model_validate(user)

    async def load_user_profile(self, user_id: int) -> User:
        """Gets a user from the database by user_id"""
        logger.info("load_user_attempt", user_id=user_id)

        user = await self.repository.get_user_by_id(user_id)

        if not user:
            raise AuthenticationError(
                error_code="user_not_found",
                message="User not found",
                log_context={
                    "event_name": "token_refresh_failed",
                    "reason": "user not found",
                    "user_id": user_id,
                },
            )

        logger.info("token_refresh_success", user_id=user.id, username=user.login)

        return User.model_validate(user)
