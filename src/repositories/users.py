from schemas.users import UserData, UserRegisterResponse
from src.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    async def create_user(self, data: UserData):
        pass
