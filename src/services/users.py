from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from src.core.security import get_password_hash
from src.schemas.users import UserRegisterResponse, UserRegisterRequest, UserData
from src.repositories.users import UserRepository
from src.services.base import BaseService


class UserService(BaseService[UserRepository]):
    async def register(self, data: UserRegisterRequest) -> UserRegisterResponse:
        password_hash = get_password_hash(data.password)

        used_data = UserData(
            login=data.login,
            email=data.email,
            password_hash=password_hash
        )

        try:
            created_user = await self.repository.create_user(used_data)
        except IntegrityError:
            raise HTTPException(status_code=409, detail="Login or email already exists")

        return UserRegisterResponse.model_validate(created_user)
