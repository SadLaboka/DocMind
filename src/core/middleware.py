import time

from typing import Any
from uuid import uuid4
from fastapi import FastAPI


class Middleware:
    """ASGI middleware for FastAPI"""
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        """Fills the state with request ID and client IP data. Intercepts the start message and adds headers"""
        if scope["type"] != "http": # processes only HTTP requests
            await self.app(scope, receive, send)
            return

        state = scope.setdefault("state", {})
        state["request_id"] = str(uuid4())
        state["client_ip"] = self._extract_client_ip(scope)

        start_time = time.perf_counter()
        initial_headers_sent = False

        async def wrapped_send(message: dict) -> None:
            nonlocal initial_headers_sent

            if message["type"] == "http.response.start" and not initial_headers_sent:
                initial_headers_sent = True
                process_time = time.perf_counter() - start_time

                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", state["request_id"].encode("latin-1")))
                headers.append((b"x-process-time", f"{process_time:.4f}".encode("latin-1")))
                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, wrapped_send)

    @staticmethod
    def _extract_client_ip(scope: dict) -> str:
        """Gets client ip from scope"""
        headers = scope.get("headers", [])
        headers_dict = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in headers
        }

        if "x-forwarded-for" in headers_dict:
            return headers_dict["x-forwarded-for"].split(",")[0].strip()
        if "x-real-ip" in headers_dict:
            return headers_dict["x-real-ip"]

        client = scope.get("client")
        return client[0] if client else "unknown"
