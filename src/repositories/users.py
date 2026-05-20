from src.schemas.users import UserData
from src.repositories.base import BaseRepository
from src.models.users import User

from sqlalchemy import select


class UserRepository(BaseRepository):
    async def create_user(self, data: UserData) -> User:

        user = User(
            login=data.login,
            email=data.email,
            password_hash=data.password_hash
        )

        self.session.add(user)
        await self.session.flush()

        return user

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.login == username))
        user = result.scalar_one_or_none()

        return user
