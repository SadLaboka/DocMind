import json
from time import time
from typing import Any
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
import structlog

from src.core.rate_limiter import get_rate_limiter
from src.core.config import settings

logger = structlog.get_logger(__name__)


class RateLimitMiddleware:
    """ASGI middleware that sets the limit on requests"""
    def __init__(self, app: Any) -> None:
        self.app = app
        self.limiter = get_rate_limiter()

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        key = self._get_key(scope)
        limit, window = self._get_limit_and_window(scope)

        try:
            is_allowed, current_count, reset_time = await self.limiter.check_rate_limit(key, limit, window)
        except Exception as err:
            logger.warning(
                "redis_unavailable_rate_limit_skipped",
                path=scope.get("path"),
                method=scope.get("method"),
                error=str(err),
            )
            await self.app(scope, receive, send)
            return

        if not is_allowed:
            identifier = scope.get("state", {}).get("client_ip", "unknown")
            logger.warning(
                "rate_limit_exceeded",
                path=scope.get("path"),
                method=scope.get("method"),
                client_ip=identifier,
                limit=limit,
                current_count=current_count,
            )
            await self._send_rate_limit_response(send, limit, reset_time)
            return

        remaining = max(0, limit - current_count)

        async def wrapped_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"x-ratelimit-limit", str(limit).encode()),
                    (b"x-ratelimit-remaining", str(remaining).encode()),
                    (b"x-ratelimit-reset", str(reset_time).encode()),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, wrapped_send)


    def _get_limit_and_window(self, scope: dict) -> tuple[int, int]:
        """Matches the path with the limit and window values from config"""
        post_map = {
            "/auth/login": (settings.rate_limit.login_limit, settings.rate_limit.login_window),
            "/users/register": (settings.rate_limit.register_limit, settings.rate_limit.register_window),
            "/documents": (settings.rate_limit.documents_post_limit, settings.rate_limit.documents_post_window),
        }

        get_map = {
            "/documents": (settings.rate_limit.documents_get_limit, settings.rate_limit.documents_get_window),
            "/documents/{id}": (settings.rate_limit.documents_get_limit, settings.rate_limit.documents_get_window),
        }

        global_values = settings.rate_limit.global_limit, settings.rate_limit.global_window

        path = scope.get("path")

        if not path:
            return global_values

        path = self._normalize_path(path)

        method = scope.get("method")

        if method == "POST":
            values = post_map.get(path)
            return values if values else global_values
        elif method == "GET":
            values = get_map.get(path)
            return values if values else global_values

        return global_values

    async def _send_rate_limit_response(
            self, send: Any, limit: int, reset_time: int
    ) -> None:
        """Sends 429 response with rate limit headers"""
        response_body = {
            "code": "rate_limit_exceeded",
            "detail": "Too many requests. Please try again later.",
        }
        body = json.dumps(response_body).encode("utf-8")

        retry_after = max(0, reset_time - int(time()))

        await send({
            "type": "http.response.start",
            "status": HTTP_429_TOO_MANY_REQUESTS,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
                (b"x-ratelimit-limit", str(limit).encode()),
                (b"x-ratelimit-remaining", b"0"),
                (b"x-ratelimit-reset", str(reset_time).encode()),
                (b"retry-after", str(retry_after).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    def _get_key(self, scope: dict) -> str:
        """Constructs the key based on the scope"""

        path = scope.get("path", "/")
        path = self._normalize_path(path)

        state = scope.get("state", {})
        identifier = state.get("client_ip", "unknown")

        method = scope.get("method", "UNKNOWN")

        return f"rate_limit:{method}:{path}:{identifier}"

    @staticmethod
    def _normalize_path(path: str) -> str:
        path = path.rstrip("/")
        parts = path.split("/")

        if len(parts) >= 3 and parts[1] == "documents":
            if parts[2].isdigit():
                if len(parts) == 3:
                    return "/documents/{id}"
                return f"/documents/{id}/{'/'.join(parts[3:])}"

        return path
