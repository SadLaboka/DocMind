from datetime import UTC, datetime, timedelta
from functools import cached_property
from pathlib import Path
from uuid import uuid4

import jwt

from src.core.config import settings
from src.core.exceptions import AuthenticationError

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class JWTManager:
    """Manager for managing the creation and processing of JWT-tokens"""

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
        """Entry point for creating a token pair.
        Splits the payload for assembling tokens and returns the resulting dictionary."""
        jti = uuid4().hex
        return {
            "access_token": self._create_access_token(payload, jti),
            "refresh_token": self._create_refresh_token(payload["sub"], jti),
            "token_type": "Bearer",
        }

    def _create_access_token(self, payload: dict, jti: str) -> str:
        """Submits a payload for gathering access token"""
        access_token = self._create_jwt(
            payload=payload,
            token_type=ACCESS_TOKEN_TYPE,
            time_delta=timedelta(minutes=settings.jwt.timedelta),
            jti=jti,
        )
        return access_token

    def _create_refresh_token(self, user_id: int, jti: str) -> str:
        """Submits a payload for gathering refresh token"""
        refresh_token = self._create_jwt(
            payload={"sub": str(user_id)},
            token_type=REFRESH_TOKEN_TYPE,
            time_delta=timedelta(days=settings.jwt.refresh_timedelta),
            jti=jti,
        )
        return refresh_token

    def _create_jwt(self, payload: dict, token_type: str, time_delta: timedelta, jti: str) -> str:
        """Gathering payload and encode it to JWT"""
        to_encode = payload.copy()
        if to_encode.get("sub"):
            to_encode["sub"] = str(to_encode["sub"])
        iat = datetime.now(UTC)
        expire = iat + time_delta
        to_encode.update({"jti": jti, "exp": expire, "iat": iat, "type": token_type})
        return jwt.encode(to_encode, self.private_key, algorithm=self.algorithm)

    def get_payload_from_access_token(self, access_token: str) -> dict:
        """Gets payload from access token"""
        payload = self.verify_token(token=access_token, token_type=ACCESS_TOKEN_TYPE)
        return payload

    def get_sub_from_refresh_token(self, refresh_token: str) -> int:
        """Gets sub value from refresh token payload"""
        payload = self.verify_token(refresh_token, REFRESH_TOKEN_TYPE)
        return int(payload["sub"])

    def verify_token(self, token: str, token_type: str) -> dict:
        """Decodes the token to verify and obtain the payload"""
        try:
            payload = jwt.decode(token, self.public_key, algorithms=[self.algorithm])
            received_token_type = payload.get("type")
            if received_token_type != token_type:
                raise AuthenticationError(
                    error_code="invalid_token_type",
                    message="Invalid token type",
                    log_context={
                        "event_name": "token_verification_failed",
                        "reason": "token type mismatch",
                        "expected_token_type": token_type,
                        "received_token_type": received_token_type,
                        "token_prefix": token[:10],
                        "subject_id": payload["sub"],
                        "expired_at": datetime.fromtimestamp(payload["exp"], UTC).isoformat(),
                    },
                )
            return payload
        except jwt.ExpiredSignatureError as raw_error:
            raise AuthenticationError(
                error_code="token_expired",
                message="Token expired",
                log_context={
                    "event_name": "token_verification_failed",
                    "reason": "token expired",
                    "token_prefix": token[:10],
                    "library_hint": str(raw_error),
                },
            ) from raw_error
        except jwt.InvalidSignatureError as raw_error:
            raise AuthenticationError(
                error_code="invalid_signature",
                message="Invalid token",
                log_context={
                    "event_name": "token_verification_failed",
                    "reason": "invalid signature",
                    "token_prefix": token[:10],
                    "library_hint": str(raw_error),
                },
            ) from raw_error
        except jwt.DecodeError as raw_error:
            raise AuthenticationError(
                error_code="decode_error",
                message="Invalid token",
                log_context={
                    "event_name": "token_verification_failed",
                    "reason": "decode error",
                    "token_prefix": token[:10],
                    "library_hint": str(raw_error),
                },
            ) from raw_error
        except jwt.InvalidAlgorithmError as raw_error:
            raise AuthenticationError(
                error_code="invalid_algorithm",
                message="Invalid token",
                log_context={
                    "event_name": "token_verification_failed",
                    "reason": "invalid algorithm",
                    "token_prefix": token[:10],
                    "algorithm": self.algorithm,
                    "library_hint": str(raw_error),
                },
            ) from raw_error
        except jwt.InvalidTokenError as raw_error:
            raise AuthenticationError(
                error_code="token_error",
                message="Invalid token",
                log_context={
                    "event_name": "token_verification_failed",
                    "reason": "invalid token",
                    "token_prefix": token[:10],
                    "library_hint": str(raw_error),
                },
            ) from raw_error
