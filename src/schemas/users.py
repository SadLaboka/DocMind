from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    login: str = Field(min_length=4, max_length=25)
    email: EmailStr


class UserRegisterRequest(UserBase):
    password: str = Field(min_length=8, max_length=64)


class UserRegisterResponse(UserBase):
    id: int

    model_config = ConfigDict(from_attributes=True)


class UserData(UserBase):
    password_hash: str


class User(BaseModel):
    id: int
    login: str
    is_admin: bool

    model_config = ConfigDict(from_attributes=True)

class UserWithStatus(User):
    is_active: bool
