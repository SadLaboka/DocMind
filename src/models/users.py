from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Boolean

from src.models.base import Base


class User(Base):
    __tablename__ = "users"

    login: Mapped[str] = mapped_column(String(25), unique=True)
    password_hash: Mapped[str]
    email: Mapped[str] = mapped_column(String(40), unique=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
