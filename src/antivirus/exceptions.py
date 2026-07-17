from typing import Any


class AntivirusException(Exception):
    message: str = "Antivirus error"
    error_code: str = "antivirus_error"
    log_context: dict[str, Any]

    def __init__(self, error_code: str | None = None, message: str | None = None, log_context: dict | None = None):
        self.error_code = error_code or type(self).error_code
        self.message = message or type(self).message
        self.log_context = log_context or {}
        super().__init__(self.message)


class AntivirusUnavailableError(AntivirusException):
    message: str = "Antivirus unavailable"
    error_code: str = "antivirus_unavailable"

    def __init__(
            self,
            host: str | None = None,
            port: int | None = None,
            error_code: str | None = None,
            message: str | None = None,
            log_context: dict | None = None,
            original_error: Exception | None = None
    ):
        super().__init__(error_code=error_code, message=message, log_context=log_context)
        self.host = host
        self.port = port
        self.original_error = original_error
