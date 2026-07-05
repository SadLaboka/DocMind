from sqlalchemy import select

from src.models.users import User
from src.repositories.base import BaseRepository
from src.schemas.users import UserData


class UserRepository(BaseRepository):
    async def create_user(self, data: UserData) -> User:

        user = User(login=data.login, email=data.email, password_hash=data.password_hash)

        self.session.add(user)
        await self.session.flush()

        return user

    async def get_user_by_username(self, username: str) -> User | None:
        result = await self.session.execute(select(User).where(User.login == username))
        user = result.scalar_one_or_none()

        return user

    async def get_user_by_id(self, user_id: int) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        return user

    async def update_is_active(self, user_id: int, is_active: bool) -> User | None:
        user = await self.get_user_by_id(user_id)
        if not user:
            return None

        user.is_active = is_active
        await self.session.commit()
        await self.session.refresh(user)

        return user
