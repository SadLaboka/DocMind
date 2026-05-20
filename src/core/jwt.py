import jwt

from datetime import datetime, timedelta, UTC
from functools import cached_property
from pathlib import Path

from fastapi import HTTPException

from src.core.config import settings


class JWTManager:
    def __init__(
            self,
            private_key_path: str = settings.jwt.private_key_path,
            public_key_path: str = settings.jwt.public_key_path,
            algorithm: str = settings.jwt.algorithm,
    ):
        self._private_key_path = Path(private_key_path)
        self._public_key_path = Path(public_key_path)
        self.algorithm = algorithm

    @cached_property
    def private_key(self) -> bytes:
        return self._private_key_path.read_bytes()

    @cached_property
    def public_key(self) -> bytes:
        return self._public_key_path.read_bytes()


    def create_access_token(self, data: dict, time_delta: float = settings.jwt.timedelta) -> str:
        to_encode = data.copy()
        expire = datetime.now(UTC) + timedelta(minutes=time_delta)
        to_encode.update({"exp": expire, "type": "access"})
        return jwt.encode(to_encode, self.private_key, algorithm=self.algorithm)


    def create_refresh_token(self, data: dict)  -> str:
        expire = datetime.now(UTC) + timedelta(days=settings.jwt.refresh_timedelta)
        to_encode = data.copy()
        to_encode.update({"exp": expire, "type": "refresh"})
        return jwt.encode(to_encode, self.private_key, algorithm=self.algorithm)


    def verify_token(self, token: str, token_type: str) -> dict:
        try:
            data = jwt.decode(token, self.public_key, algorithms=[self.algorithm])
            if data.get("type") != token_type:
                raise jwt.InvalidTokenError(f"Invalid token_type: expected {token_type}")
            return data
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token expired")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token")
