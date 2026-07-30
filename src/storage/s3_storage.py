import contextlib
import mimetypes
from pathlib import Path
from typing import NoReturn
from urllib import parse

import aioboto3
from botocore.exceptions import BotoCoreError, ClientError

from src.core.config import settings
from src.storage.exceptions import (
    S3ConnectionError,
    S3FileNotFoundError,
    S3PresignedUrlError,
    S3UploadError,
    StorageError,
)


class S3Storage:
    """S3-compatible storage client"""

    MAX_PRESIGNED_URL_TTL = 3600

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str,
        bucket: str,
        presigned_url_ttl: int = 3600,
        sse_enabled: bool = False,
        external_endpoint_url: str | None = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._external_endpoint_url = external_endpoint_url or endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._bucket = bucket
        self._presigned_url_ttl = presigned_url_ttl
        self._sse_enabled = sse_enabled
        self._session = aioboto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    @contextlib.asynccontextmanager
    async def _get_client(self, endpoint_url: str | None = None):
        """Create S3 client context manager"""
        endpoint_url = endpoint_url or self._endpoint_url
        async with self._session.client("s3", endpoint_url=endpoint_url) as client:
            yield client

    async def upload_file(self, file_path: Path, key: str) -> str:
        """Upload file to S3 with SSE-S3 encryption, return key"""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content_type = self._get_content_type(file_path)

        extra_args = {"ContentType": content_type}
        if self._sse_enabled:
            extra_args["ServerSideEncryption"] = "AES256"

        async with self._get_client() as client:
            try:
                await client.upload_file(
                    Filename=str(file_path),
                    Bucket=self._bucket,
                    Key=key,
                    ExtraArgs=extra_args,
                )

                return key
            except ClientError as e:
                self._handle_boto_error(e, "upload_file", key)

    async def delete_file(self, key: str) -> bool:
        """Delete file from S3, return True if deleted"""
        async with self._get_client() as client:
            try:
                await client.delete_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as e:
                self._handle_boto_error(e, "delete_file", key)

    async def file_exists(self, key: str) -> bool:
        """Check if file exists in S3 via HEAD request"""
        async with self._get_client() as client:
            try:
                await client.head_object(Bucket=self._bucket, Key=key)
                return True
            except ClientError as e:
                error_code = e.response["Error"]["Code"]
                if error_code in ("404", "NoSuchKey"):
                    return False
                self._handle_boto_error(e, "file_exists", key)

    async def generate_presigned_url(
        self,
        key: str,
        expires_in: int | None = None,
        original_filename: str | None = None,
    ) -> str:
        if not key:
            raise ValueError("key must not be empty")

        target_ttl = expires_in if expires_in is not None else self._presigned_url_ttl

        if target_ttl <= 0 or target_ttl > self.MAX_PRESIGNED_URL_TTL:
            raise ValueError(f"expires_in must be between 1 and {self.MAX_PRESIGNED_URL_TTL} seconds")

        params = {"Bucket": self._bucket, "Key": key}

        if original_filename:
            encoded_name = parse.quote(original_filename)
            params["ResponseContentDisposition"] = f"attachment; filename*=UTF-8''{encoded_name}"

        url_endpoint = self._external_endpoint_url

        async with self._get_client(url_endpoint) as client:
            try:
                url = await client.generate_presigned_url(
                    "get_object",
                    Params=params,
                    ExpiresIn=target_ttl,
                )
                return url
            except BotoCoreError as e:
                raise S3PresignedUrlError(
                    message=f"Failed to generate presigned URL for key: {key}",
                    original_error=e,
                    key=key,
                ) from e

    def _handle_boto_error(self, error: ClientError, operation: str, key: str | None = None) -> NoReturn:
        """Convert botocore ClientError to custom storage exceptions"""
        error_code = error.response["Error"]["Code"]
        error_message = error.response["Error"]["Message"]

        log_context = {
            "operation": operation,
            "key": key,
            "bucket": self._bucket,
            "aws_error_code": error_code,
            "aws_error_message": error_message,
        }

        if error_code in ("404", "NoSuchKey", "NoSuchBucket"):
            raise S3FileNotFoundError(
                message=f"File not found: {key}",
                log_context=log_context,
                key=key,
                operation=operation,
            ) from error

        if error_code in ("403", "AccessDenied"):
            raise S3UploadError(
                message=f"Access denied: {key}",
                retryable=False,
                log_context=log_context,
                key=key,
                original_error=error,
            ) from error

        if error_code in ("500", "503", "SlowDown", "InternalError", "ServiceUnavailable"):
            raise S3ConnectionError(
                message=f"S3 server error: {error_message}",
                log_context=log_context,
                original_error=error,
                operation=operation,
            ) from error

        if operation == "upload_file":
            raise S3UploadError(
                message=f"Upload failed: {error_message}",
                log_context=log_context,
                key=key,
                original_error=error,
            ) from error

        raise StorageError(
            message=f"Storage operation failed: {error_message}",
            log_context=log_context,
            original_error=error,
        ) from error

    @staticmethod
    def _get_content_type(file_path: Path) -> str:
        """Determine content type from file extension"""
        content_type, _ = mimetypes.guess_type(str(file_path))
        return content_type or "application/octet-stream"


_storage_instance: S3Storage | None = None


def get_storage() -> S3Storage:
    """Returns singleton S3Storage instance based on active storage config"""
    global _storage_instance
    if _storage_instance is None:
        storage_config = settings.storage
        _storage_instance = S3Storage(
            endpoint_url=storage_config.endpoint_url,
            access_key=storage_config.access_key,
            secret_key=storage_config.secret_key,
            region=storage_config.region,
            bucket=storage_config.bucket,
            presigned_url_ttl=storage_config.presigned_url_ttl,
            sse_enabled=storage_config.sse_enabled,
            external_endpoint_url=storage_config.external_endpoint_url,
        )
    return _storage_instance
