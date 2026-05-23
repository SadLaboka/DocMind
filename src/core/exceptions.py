class AppBaseError(Exception):
    status_code: int = 500
    error_code: str = "Internal_error"
    message: str = "Internal server error"
    log_context: dict | None = None

    def __init__(self, error_code: str | None = None, message: str | None = None, log_context: dict | None = None):
        self.error_code = error_code if error_code else type(self).error_code
        self.message = message if message else type(self).message
        self.log_context = log_context if log_context else {}
        super().__init__(self.message)


class AuthenticationError(AppBaseError):
    status_code = 401
    error_code =  "unauthorized"
    message = "Invalid credentials"


class ResourceNotFoundError(AppBaseError):
    status_code = 404
    error_code = "not_found"
    message = "Resource not found"


class ConflictError(AppBaseError):
    status_code = 409
    error_code = "conflict"
    message = "Resource already exists"
