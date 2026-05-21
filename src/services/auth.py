from fastapi import HTTPException

from src.core.security import check_password
from src.repositories.users import UserRepository
from src.schemas.users import User
from src.services.base import BaseService


class AuthService(BaseService[UserRepository]):
    async def authenticate(self, username: str, password: str) -> User:
        user = await self.repository.get_user_by_username(username)
        if not user or not check_password(password, user.password_hash):
            raise HTTPException(status_code=401, detail="Incorrect username or password")
        return User.model_validate(user)

    async def get_current_user(self, user_id: int) -> User:
        user = await self.repository.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return User.model_validate(user)
