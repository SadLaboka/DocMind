from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path

import jwt
from fastapi import HTTPException

from src.core.config import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


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

    def get_tokens(self, payload: dict) -> dict:
        return {"access_token": self._create_access_token(payload),
                "refresh_token": self._create_refresh_token(payload["sub"]),
                "token_type": "Bearer"}

    def _create_access_token(self, payload: dict) -> str:
        access_token = self._create_jwt(
            payload=payload,
            token_type=ACCESS_TOKEN_TYPE,
            time_delta=timedelta(minutes=settings.jwt.timedelta)
        )
        return access_token

    def _create_refresh_token(self, user_id: int)  -> str:
        refresh_token = self._create_jwt(
            payload={"sub": user_id},
            token_type=REFRESH_TOKEN_TYPE,
            time_delta=timedelta(days=settings.jwt.refresh_timedelta)
        )
        return refresh_token

    def _create_jwt(self, payload: dict, token_type: str, time_delta: timedelta) -> str:
        to_encode = payload.copy()
        iat = datetime.now(UTC)
        expire = iat + time_delta
        to_encode.update({"exp": expire, "iat": iat, "type": token_type})
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
