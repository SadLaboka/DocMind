from typing import Any, NoReturn


class StorageError(Exception):
    """Base exception for all storage-related errors"""

    message: str = "Storage error"
    error_code: str = "storage_error"
    retryable: bool = False
    log_context: dict[str, Any]

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        log_context: dict[str, Any] | None = None,
        original_error: Exception | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.error_code = error_code or type(self).error_code
        self.retryable = retryable if retryable is not None else type(self).retryable
        self.log_context = log_context or {}
        self.original_error = original_error
        super().__init__(self.message)


class S3ConnectionError(StorageError):
    """S3 connection error (timeout, network error, 5xx)"""

    message: str = "S3 connection error"
    error_code: str = "s3_connection_error"
    retryable: bool = True

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        log_context: dict[str, Any] | None = None,
        original_error: Exception | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message, error_code, retryable, log_context, original_error)
        self.operation = operation


class S3UploadError(StorageError):
    """S3 upload error"""

    message: str = "S3 upload error"
    error_code: str = "s3_upload_error"
    retryable: bool = True

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        retryable: bool | None = None,
        log_context: dict[str, Any] | None = None,
        original_error: Exception | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(message, error_code, retryable, log_context, original_error)
        self.key = key


class S3FileNotFoundError(StorageError):
    """S3 file not found (404 / NoSuchKey)"""

    message: str = "S3 file not found"
    error_code: str = "s3_file_not_found"
    retryable: bool = False

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        log_context: dict[str, Any] | None = None,
        key: str | None = None,
        operation: str | None = None,
    ) -> None:
        super().__init__(message, error_code, retryable=False, log_context=log_context)
        self.key = key
        self.operation = operation


class S3PresignedUrlError(StorageError):
    """S3 presigned URL generation error"""

    message: str = "S3 presigned URL generation error"
    error_code: str = "s3_presigned_url_error"
    retryable: bool = True

    def __init__(
        self,
        message: str | None = None,
        error_code: str | None = None,
        log_context: dict[str, Any] | None = None,
        original_error: Exception | None = None,
        key: str | None = None,
    ) -> None:
        super().__init__(
            message, error_code, retryable=True, log_context=log_context, original_error=original_error
        )
        self.key = key


class StorageConfigError(StorageError):
    """Storage configuration error (missing credentials, invalid endpoint, etc.)"""

    message: str = "Storage configuration error"
    error_code: str = "storage_config_error"
    retryable: bool = False
