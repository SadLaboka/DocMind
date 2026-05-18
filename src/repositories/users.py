from src.schemas.users import UserData
from src.repositories.base import BaseRepository
from src.models.users import User


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
