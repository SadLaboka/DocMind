from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from botocore.exceptions import BotoCoreError, ClientError

from src.storage.exceptions import (
    S3ConnectionError,
    S3FileNotFoundError,
    S3PresignedUrlError,
    S3UploadError,
    StorageError,
)
from src.storage.s3_storage import S3Storage, get_storage


def _make_client_error(code: str, message: str = "error") -> ClientError:
    """Helper to create botocore ClientError"""
    return ClientError({"Error": {"Code": code, "Message": message}}, "operation_name")


def _mock_get_client(mock_client):
    """Helper to create a mock async context manager for _get_client"""

    @asynccontextmanager
    async def _mock(endpoint_url: str | None = None):
        yield mock_client

    return _mock


# ==================== upload_file ====================


@pytest.mark.asyncio
async def test_upload_file_success(s3_storage, temp_file, mock_s3_client):
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    result = await s3_storage.upload_file(temp_file, "test/test.txt")

    assert result == "test/test.txt"
    mock_s3_client.upload_file.assert_called_once_with(
        Filename=str(temp_file),
        Bucket="test-bucket",
        Key="test/test.txt",
        ExtraArgs={
            "ContentType": "text/plain",
        },
    )


@pytest.mark.asyncio
async def test_upload_file_not_found(s3_storage):
    from pathlib import Path

    non_existent = Path("/nonexistent/file.txt")

    with pytest.raises(FileNotFoundError):
        await s3_storage.upload_file(non_existent, "test.txt")


@pytest.mark.asyncio
async def test_upload_file_client_error_403(s3_storage, temp_file, mock_s3_client):
    mock_s3_client.upload_file.side_effect = _make_client_error("403", "Access Denied")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    with pytest.raises(S3UploadError) as exc_info:
        await s3_storage.upload_file(temp_file, "test.txt")

    assert exc_info.value.retryable is False


@pytest.mark.asyncio
async def test_upload_file_client_error_500(s3_storage, temp_file, mock_s3_client):
    mock_s3_client.upload_file.side_effect = _make_client_error("500", "Internal Error")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    with pytest.raises(S3ConnectionError) as exc_info:
        await s3_storage.upload_file(temp_file, "test.txt")

    assert exc_info.value.retryable is True


# ==================== delete_file ====================


@pytest.mark.asyncio
async def test_delete_file_success(s3_storage, mock_s3_client):
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    result = await s3_storage.delete_file("test.txt")

    assert result is True
    mock_s3_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")


@pytest.mark.asyncio
async def test_delete_file_client_error(s3_storage, mock_s3_client):
    mock_s3_client.delete_object.side_effect = _make_client_error("500")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    with pytest.raises(S3ConnectionError):
        await s3_storage.delete_file("test.txt")


# ==================== file_exists ====================


@pytest.mark.asyncio
async def test_file_exists_true(s3_storage, mock_s3_client):
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    result = await s3_storage.file_exists("test.txt")

    assert result is True
    mock_s3_client.head_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")


@pytest.mark.asyncio
async def test_file_exists_false_404(s3_storage, mock_s3_client):
    mock_s3_client.head_object.side_effect = _make_client_error("404")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    result = await s3_storage.file_exists("test.txt")

    assert result is False


@pytest.mark.asyncio
async def test_file_exists_false_no_such_key(s3_storage, mock_s3_client):
    mock_s3_client.head_object.side_effect = _make_client_error("NoSuchKey")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    result = await s3_storage.file_exists("test.txt")

    assert result is False


@pytest.mark.asyncio
async def test_file_exists_client_error_500(s3_storage, mock_s3_client):
    mock_s3_client.head_object.side_effect = _make_client_error("500")
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    with pytest.raises(S3ConnectionError):
        await s3_storage.file_exists("test.txt")


# ==================== generate_presigned_url ====================


@pytest.mark.asyncio
async def test_generate_presigned_url_success(s3_storage, mock_s3_client):
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    url = await s3_storage.generate_presigned_url("test.txt")

    assert url == "https://signed-url"
    mock_s3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "test.txt"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_generate_presigned_url_custom_ttl(s3_storage, mock_s3_client):
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    await s3_storage.generate_presigned_url("test.txt", expires_in=1800)

    mock_s3_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "test.txt"},
        ExpiresIn=1800,
    )


@pytest.mark.asyncio
async def test_generate_presigned_url_empty_key(s3_storage):
    with pytest.raises(ValueError, match="key must not be empty"):
        await s3_storage.generate_presigned_url("")


@pytest.mark.asyncio
async def test_generate_presigned_url_invalid_ttl_zero(s3_storage):
    with pytest.raises(ValueError, match="expires_in must be between"):
        await s3_storage.generate_presigned_url("test.txt", expires_in=0)


@pytest.mark.asyncio
async def test_generate_presigned_url_invalid_ttl_negative(s3_storage):
    with pytest.raises(ValueError, match="expires_in must be between"):
        await s3_storage.generate_presigned_url("test.txt", expires_in=-1)


@pytest.mark.asyncio
async def test_generate_presigned_url_invalid_ttl_too_large(s3_storage):
    with pytest.raises(ValueError, match="expires_in must be between"):
        await s3_storage.generate_presigned_url("test.txt", expires_in=999999)


@pytest.mark.asyncio
async def test_generate_presigned_url_boto_error(s3_storage, mock_s3_client):
    mock_s3_client.generate_presigned_url.side_effect = BotoCoreError()
    s3_storage._get_client = _mock_get_client(mock_s3_client)

    with pytest.raises(S3PresignedUrlError) as exc_info:
        await s3_storage.generate_presigned_url("test.txt")

    assert exc_info.value.key == "test.txt"
    assert isinstance(exc_info.value.original_error, BotoCoreError)


# ==================== _get_content_type ====================


def test_get_content_type_txt(s3_storage, tmp_path):
    file = tmp_path / "test.txt"
    file.write_text("test")
    assert s3_storage._get_content_type(file) == "text/plain"


def test_get_content_type_pdf(s3_storage, tmp_path):
    file = tmp_path / "test.pdf"
    file.write_bytes(b"%PDF-1.4")
    assert s3_storage._get_content_type(file) == "application/pdf"


def test_get_content_type_unknown(s3_storage, tmp_path):
    file = tmp_path / "test.unknownext"
    file.write_text("test")
    assert s3_storage._get_content_type(file) == "application/octet-stream"


# ==================== _handle_boto_error ====================


def test_handle_boto_error_404(s3_storage):
    error = _make_client_error("404")
    with pytest.raises(S3FileNotFoundError):
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")


def test_handle_boto_error_no_such_key(s3_storage):
    error = _make_client_error("NoSuchKey")
    with pytest.raises(S3FileNotFoundError):
        s3_storage._handle_boto_error(error, "download_file", "test.txt")


def test_handle_boto_error_no_such_bucket(s3_storage):
    error = _make_client_error("NoSuchBucket")
    with pytest.raises(S3FileNotFoundError):
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")


def test_handle_boto_error_403(s3_storage):
    error = _make_client_error("403")
    with pytest.raises(S3UploadError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is False


def test_handle_boto_error_access_denied(s3_storage):
    error = _make_client_error("AccessDenied")
    with pytest.raises(S3UploadError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is False


def test_handle_boto_error_500(s3_storage):
    error = _make_client_error("500")
    with pytest.raises(S3ConnectionError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is True


def test_handle_boto_error_503(s3_storage):
    error = _make_client_error("503")
    with pytest.raises(S3ConnectionError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is True


def test_handle_boto_error_slow_down(s3_storage):
    error = _make_client_error("SlowDown")
    with pytest.raises(S3ConnectionError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is True


def test_handle_boto_error_internal_error(s3_storage):
    error = _make_client_error("InternalError")
    with pytest.raises(S3ConnectionError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is True


def test_handle_boto_error_service_unavailable(s3_storage):
    error = _make_client_error("ServiceUnavailable")
    with pytest.raises(S3ConnectionError) as exc_info:
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")
    assert exc_info.value.retryable is True


def test_handle_boto_error_upload_fallback(s3_storage):
    error = _make_client_error("SomeUnknownError")
    with pytest.raises(S3UploadError):
        s3_storage._handle_boto_error(error, "upload_file", "test.txt")


def test_handle_boto_error_generic(s3_storage):
    error = _make_client_error("SomeUnknownError")
    with pytest.raises(StorageError):
        s3_storage._handle_boto_error(error, "some_other_operation", "test.txt")


# ==================== get_storage (singleton) ====================


def test_get_storage_returns_s3_storage():
    with patch("src.storage.s3_storage.settings") as mock_settings:
        mock_settings.storage.endpoint_url = "http://localhost:9000"
        mock_settings.storage.access_key = "test"
        mock_settings.storage.secret_key = "test"
        mock_settings.storage.region = "us-east-1"
        mock_settings.storage.bucket = "test-bucket"
        mock_settings.storage.presigned_url_ttl = 3600

        import src.storage.s3_storage as module

        module._storage_instance = None

        storage = get_storage()
        assert isinstance(storage, S3Storage)


def test_get_storage_singleton():
    with patch("src.storage.s3_storage.settings") as mock_settings:
        mock_settings.storage.endpoint_url = "http://localhost:9000"
        mock_settings.storage.access_key = "test"
        mock_settings.storage.secret_key = "test"
        mock_settings.storage.region = "us-east-1"
        mock_settings.storage.bucket = "test-bucket"
        mock_settings.storage.presigned_url_ttl = 3600

        import src.storage.s3_storage as module

        module._storage_instance = None

        storage1 = get_storage()
        storage2 = get_storage()
        assert storage1 is storage2
