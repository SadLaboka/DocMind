from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.core.enums import DocumentStatus
from src.storage.exceptions import (
    S3ConnectionError,
    S3UploadError,
    StorageConfigError,
    StorageError,
)
from src.storage.s3_storage import S3Storage
from src.worker.s3_upload_task import (
    UploadTask,
    extract_text_task,
)

EXPECTED_FILE_KEY = "documents/test.txt"


@pytest.fixture
def mock_storage() -> AsyncMock:
    mock_storage = AsyncMock(spec=S3Storage)
    mock_storage.file_exists.return_value = False
    return mock_storage


@pytest.fixture
def upload_task(mock_storage: AsyncMock) -> UploadTask:
    with patch(
        "src.worker.s3_upload_task.get_storage",
        return_value=mock_storage,
    ):
        return UploadTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            mime_type="text/plain",
            user_id=2,
            request_id="req-123",
            provider="gemini",
        )


@pytest.fixture
def mock_extraction_publisher():
    with patch(
        "src.worker.s3_upload_task.asyncio.to_thread",
        new_callable=AsyncMock,
    ) as mock_to_thread:
        yield mock_to_thread


@pytest.mark.asyncio
async def test_execute_success_uploads_file_and_enqueues_extraction(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    await upload_task.execute()

    mock_worker_repo.update_document_fields.assert_awaited_with(
        document_id=upload_task.document_id,
        file_key=EXPECTED_FILE_KEY,
        document_status=DocumentStatus.uploaded,
    )

    mock_storage.upload_file.assert_awaited_once_with(
        upload_task.temp_path,
        EXPECTED_FILE_KEY,
    )

    mock_extraction_publisher.assert_awaited_once_with(
        extract_text_task.delay,
        document_id=upload_task.document_id,
        temp_path=str(upload_task.temp_path),
        mime_type=upload_task.mime_type,
        user_id=upload_task.user_id,
        request_id=upload_task.request_id,
        provider=upload_task.provider,
    )

    mock_unlink.assert_not_called()


@pytest.mark.asyncio
async def test_execute_storage_config_error_marks_failed_and_removes_file(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_storage.upload_file.side_effect = StorageConfigError(
        message="Missing credentials",
    )

    await upload_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            document_id=upload_task.document_id,
            document_status=DocumentStatus.uploading,
        ),
        call(
            document_id=upload_task.document_id,
            document_status=DocumentStatus.failed,
            temp_filename=None,
            error_trace="Storage configuration error",
        ),
    ]

    mock_unlink.assert_called_once_with(missing_ok=True)
    mock_extraction_publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_non_retryable_upload_error_marks_failed(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_storage.upload_file.side_effect = S3UploadError(
        message="Invalid upload request",
        retryable=False,
        key=EXPECTED_FILE_KEY,
    )

    await upload_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            document_id=upload_task.document_id,
            document_status=DocumentStatus.uploading,
        ),
        call(
            document_id=upload_task.document_id,
            document_status=DocumentStatus.failed,
            temp_filename=None,
            error_trace="S3 Upload Error: Invalid upload request",
        ),
    ]

    mock_unlink.assert_called_once_with(missing_ok=True)
    mock_extraction_publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_retryable_upload_error_propagates_and_preserves_file(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    upload_error = S3UploadError(
        message="Temporary upload failure",
        retryable=True,
        key=EXPECTED_FILE_KEY,
    )
    mock_storage.upload_file.side_effect = upload_error

    with pytest.raises(S3UploadError) as exc_info:
        await upload_task.execute()

    assert exc_info.value is upload_error

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=upload_task.document_id,
        document_status=DocumentStatus.uploading,
    )

    mock_unlink.assert_not_called()
    mock_extraction_publisher.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "storage_error",
    [
        S3ConnectionError(message="Connection timeout"),
        StorageError(message="Generic storage failure"),
        RuntimeError("Unexpected failure"),
    ],
    ids=[
        "connection-error",
        "storage-error",
        "unexpected-error",
    ],
)
async def test_execute_retryable_or_unexpected_error_propagates(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
    storage_error: Exception,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_storage.upload_file.side_effect = storage_error

    with pytest.raises(type(storage_error)) as exc_info:
        await upload_task.execute()

    assert exc_info.value is storage_error

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=upload_task.document_id,
        document_status=DocumentStatus.uploading,
    )

    mock_unlink.assert_not_called()
    mock_extraction_publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_cancelled_document_skips_upload(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.cancelled,
    )

    await upload_task.execute()

    mock_storage.upload_file.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_extraction_publisher.assert_not_awaited()
    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_execute_missing_document_skips_upload(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = None

    await upload_task.execute()

    mock_storage.upload_file.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_extraction_publisher.assert_not_awaited()
    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_execute_missing_file_marks_document_cancelled(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_storage,
    upload_task,
    mock_extraction_publisher,
) -> None:
    mock_exists, mock_unlink = mock_path_operations
    mock_exists.return_value = False

    await upload_task.execute()

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        upload_task.document_id,
        document_status=DocumentStatus.cancelled,
    )

    mock_storage.upload_file.assert_not_awaited()
    mock_extraction_publisher.assert_not_awaited()
    mock_unlink.assert_not_called()
