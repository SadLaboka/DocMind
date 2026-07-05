import structlog

from src.core.user_active_cache import UserActiveStatusCache
from src.core.exceptions import AuthenticationError
from src.core.jwt import REFRESH_TOKEN_TYPE, JWTManager
from src.core.security import check_password
from src.core.token_blacklist import TokenBlackList
from src.repositories.users import UserRepository
from src.schemas.users import User
from src.services.base import BaseService

logger = structlog.get_logger(__name__)


class AuthService(BaseService[UserRepository]):
    """Service for authentication"""

    def __init__(
            self,
            repository: UserRepository,
            token_blacklist: TokenBlackList,
            user_active_cache: UserActiveStatusCache
    ):
        super().__init__(repository)
        self.user_active_cache = user_active_cache
        self.token_blacklist = token_blacklist

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

        if not user.is_active:
            raise AuthenticationError(
                error_code="user_deactivated",
                message="User account has been deactivated",
                log_context={
                    "event_name": "login_failed_deactivated",
                    "username": username,
                    "user_id": user.id,
                },
            )

        logger.info(
            "login_success",
            user_id=user.id,
            login=user.login,
            is_admin=user.is_admin,
        )

        await self.user_active_cache.set_active(user.id, user.is_active)

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

    async def logout(self, jti: str, ttl: int) -> None:
        """Adds token to blacklist"""
        await self.token_blacklist.add_to_blacklist(jti, ttl)

    async def verify_refresh_token(self, refresh_token: str, jwt_manager: JWTManager) -> User:
        """Verifies refresh token and checks blacklist"""
        payload = jwt_manager.verify_token(refresh_token, REFRESH_TOKEN_TYPE)

        jti = payload.get("jti")
        if jti and await self.token_blacklist.is_blacklisted(jti):
            raise AuthenticationError(
                error_code="token_revoked",
                message="Refresh token has been revoked",
                log_context={
                    "event_name": "refresh_token_blacklisted",
                    "jti": jti,
                    "user_id": payload["sub"],
                },
            )

        user_id = int(payload["sub"])
        return await self.load_user_profile(user_id)
