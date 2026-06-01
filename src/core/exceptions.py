from typing import Any

from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_404_NOT_FOUND,
    HTTP_409_CONFLICT,
    HTTP_500_INTERNAL_SERVER_ERROR,
)


class AppBaseError(Exception):
    status_code: int = HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "Internal_error"
    message: str = "Internal server error"
    log_context: dict[str, Any]

    def __init__(self, error_code: str | None = None, message: str | None = None, log_context: dict | None = None):
        self.error_code = error_code or type(self).error_code
        self.message = message or type(self).message
        self.log_context = log_context or {}
        super().__init__(self.message)


class AuthenticationError(AppBaseError):
    status_code = HTTP_401_UNAUTHORIZED
    error_code = "unauthorized"
    message = "Invalid credentials"


class ResourceNotFoundError(AppBaseError):
    status_code = HTTP_404_NOT_FOUND
    error_code = "not_found"
    message = "Resource not found"


class ConflictError(AppBaseError):
    status_code = HTTP_409_CONFLICT
    error_code = "conflict"
    message = "Resource already exists"


class BadRequestError(AppBaseError):
    status_code = HTTP_400_BAD_REQUEST
    error_code = "bad_request"
    message = "Bad request"


class ExtractionError(ValueError):
    error_code = "extraction_error"
    log_context: dict[str, Any]

    def __init__(self, error_code: str | None = None,  log_context: dict | None = None):
        self.error_code = error_code or type(self).error_code
        self.log_context = log_context or {}
        super().__init__()
