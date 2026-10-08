from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.enums import DocumentStatus
from src.core.exceptions import ExtractionError
from src.worker.extraction_tasks import DocumentExtractionTask
from src.storage.exceptions import (
    S3ConnectionError,
    S3FileNotFoundError,
    StorageError,
)
from src.storage.s3_storage import S3Storage


FILE_KEY = "documents/test.txt"


class MockException(Exception):
    pass


@pytest.fixture
def mock_extraction_storage():
    storage = AsyncMock(spec=S3Storage)
    storage.download_file.return_value = True

    with patch(
        "src.worker.extraction_tasks.get_storage",
        return_value=storage,
    ):
        yield storage


@pytest.fixture
def mock_mongo_repo():
    with patch(
        "src.worker.extraction_tasks.MongoDocumentRepository",
    ) as mock_repo_class:
        mock_instance = AsyncMock()
        mock_repo_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_analysis_repo_worker():
    with patch(
        "src.worker.extraction_tasks.MongoAnalysisRepository",
    ) as mock_repo_class:
        mock_instance = AsyncMock()

        mock_instance.get_analysis_by_document_and_request.return_value = None
        mock_instance.create_analysis.return_value = MagicMock(
            id="mock-analysis-id",
        )

        mock_repo_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_analysis_service_worker():
    with patch(
        "src.worker.extraction_tasks.AnalysisService",
    ) as mock_service_class:
        mock_service = AsyncMock()
        mock_service.get_or_create_analysis.return_value = MagicMock(
            id="mock-analysis-id",
        )

        mock_service_class.return_value = mock_service
        yield mock_service


@pytest.fixture
def mock_init_mongo():
    with patch(
        "src.worker.extraction_tasks.init_mongo_for_worker",
    ) as mock_init:
        mock_init.return_value = None
        yield mock_init


@pytest.fixture
def mock_publisher():
    with patch(
        "src.worker.extraction_tasks.publish_document_analysis_requested",
    ) as mock_publish:
        yield mock_publish


@pytest.fixture
def extraction_document(mock_worker_repo):
    document = MagicMock(
        document_status=DocumentStatus.uploaded,
        file_key=FILE_KEY,
    )
    mock_worker_repo.get_document_by_id.return_value = document
    return document


@pytest.mark.asyncio
async def test_execute_success(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_analysis_service_worker,
    mock_extraction_storage,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
) -> None:
    _, mock_unlink = mock_path_operations

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        return_value="Mocked extracted text",
    ):
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_mongo_repo.upsert_raw_text.assert_awaited_once_with(
        document_id=1,
        raw_text="Mocked extracted text",
    )

    mock_worker_repo.update_document_fields.assert_any_await(
        document_id=1,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )

    mock_publisher.assert_called_once_with(
        analysis_id="mock-analysis-id",
        document_id=1,
        user_id=1,
        request_id="req-123",
    )

    mock_unlink.assert_called_with(missing_ok=True)
    mock_extraction_storage.download_file.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_document_already_cancelled(
    mock_celery_session,
    mock_mongo_repo,
    mock_init_mongo,
    mock_worker_repo,
    mock_analysis_repo_worker,
    mock_path_operations,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.cancelled,
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extract.assert_not_called()
    mock_unlink.assert_called_with(missing_ok=True)
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_extraction_hard_fail(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_init_mongo,
    mock_path_operations,
    extraction_document,
) -> None:
    _, mock_unlink = mock_path_operations

    extraction_error = ExtractionError(
        error_code="invalid_file",
        log_context={"detail": "bad pdf structure"},
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        side_effect=extraction_error,
    ):
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/bad.pdf",
            user_id=1,
            mime_type="application/pdf",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_worker_repo.update_document_fields.assert_any_await(
        document_id=1,
        document_status=DocumentStatus.failed,
        error_trace="{'detail': 'bad pdf structure'}",
        temp_filename=None,
    )

    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_unlink.assert_called_with(missing_ok=True)


@pytest.mark.asyncio
async def test_process_extraction_soft_fail(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_init_mongo,
    mock_path_operations,
    extraction_document,
) -> None:
    _, mock_unlink = mock_path_operations

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        side_effect=RuntimeError("Connection lost"),
    ):
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        with pytest.raises(RuntimeError, match="Connection lost"):
            await task.execute()

    update_calls = [
        awaited_call.kwargs
        for awaited_call in mock_worker_repo.update_document_fields.await_args_list
    ]

    assert not any(
        update_call.get("document_status") == DocumentStatus.failed
        for update_call in update_calls
    )

    mock_unlink.assert_not_called()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_status_after_failure(
    mock_celery_session,
    mock_worker_repo,
) -> None:
    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.extracting,
    )

    await DocumentExtractionTask._update_status_after_failure(
        document_id=1,
        exc=MockException(
            "Task failed after 3 retries: Connection lost",
        ),
    )

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=1,
        document_status=DocumentStatus.failed,
        temp_filename=None,
        error_trace=(
            "Task failed after all retries: "
            "Task failed after 3 retries: Connection lost"
        ),
    )


@pytest.mark.asyncio
async def test_execute_missing_local_file_restores_from_s3_and_extracts(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_analysis_service_worker,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    mock_exists, mock_unlink = mock_path_operations

    # Первый exists() — локального файла нет.
    # Второй — после успешного restore файл считается восстановленным
    # и cleanup должен его удалить.
    mock_exists.side_effect = [False, True]

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        return_value="Restored extracted text",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extraction_storage.download_file.assert_awaited_once_with(
        FILE_KEY,
        task.temp_path,
    )

    mock_extract.assert_called_once()

    mock_mongo_repo.upsert_raw_text.assert_awaited_once_with(
        document_id=1,
        raw_text="Restored extracted text",
    )

    mock_worker_repo.update_document_fields.assert_any_await(
        document_id=1,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )

    mock_publisher.assert_called_once_with(
        analysis_id="mock-analysis-id",
        document_id=1,
        user_id=1,
        request_id="req-123",
    )

    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_process_extraction_file_disappears_after_exists_restores_and_retries_once(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_analysis_service_worker,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    _, mock_unlink = mock_path_operations

    file_not_found_error = ExtractionError(
        error_code="file_not_found",
        log_context={"detail": "local file disappeared"},
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        side_effect=[
            file_not_found_error,
            "Restored extracted text",
        ],
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    assert mock_extract.call_count == 2

    mock_extraction_storage.download_file.assert_awaited_once_with(
        FILE_KEY,
        task.temp_path,
    )

    mock_mongo_repo.upsert_raw_text.assert_awaited_once_with(
        document_id=1,
        raw_text="Restored extracted text",
    )

    mock_worker_repo.update_document_fields.assert_any_await(
        document_id=1,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )

    mock_publisher.assert_called_once_with(
        analysis_id="mock-analysis-id",
        document_id=1,
        user_id=1,
        request_id="req-123",
    )

    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_process_extraction_second_file_not_found_does_not_restore_twice(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_init_mongo,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    first_error = ExtractionError(
        error_code="file_not_found",
        log_context={"detail": "local file disappeared"},
    )
    second_error = ExtractionError(
        error_code="file_not_found",
        log_context={"detail": "restored file disappeared"},
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
        side_effect=[
            first_error,
            second_error,
        ],
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        with pytest.raises(ExtractionError) as exc_info:
            await task.execute()

    assert exc_info.value is second_error
    assert mock_extract.call_count == 2

    mock_extraction_storage.download_file.assert_awaited_once_with(
        FILE_KEY,
        task.temp_path,
    )

    mock_mongo_repo.upsert_raw_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_missing_local_file_and_file_key_raises_permanent_extraction_error(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    mock_exists, _ = mock_path_operations
    mock_exists.return_value = False

    extraction_document.file_key = None

    task = DocumentExtractionTask(
        document_id=1,
        temp_path="/tmp/test.txt",
        user_id=1,
        mime_type="text/plain",
        request_id="req-123",
        provider="gemini",
    )

    with pytest.raises(ExtractionError) as exc_info:
        await task.execute()

    assert exc_info.value.error_code == "file_and_key_is_missing"

    mock_extraction_storage.download_file.assert_not_awaited()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_s3_file_not_found_marks_document_failed(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    mock_exists, _ = mock_path_operations
    mock_exists.return_value = False

    storage_error = S3FileNotFoundError(
        message="Object is missing",
        key=FILE_KEY,
        operation="download_file",
    )
    mock_extraction_storage.download_file.side_effect = storage_error

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extraction_storage.download_file.assert_awaited_once_with(
        FILE_KEY,
        task.temp_path,
    )

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=1,
        document_status=DocumentStatus.failed,
        temp_filename=None,
        error_trace=(
            "Document file is missing. "
            "S3 download Error: Object is missing"
        ),
    )

    mock_extract.assert_not_called()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_publisher.assert_not_called()


@pytest.mark.asyncio
async def test_execute_non_retryable_storage_error_marks_document_failed(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    mock_exists, _ = mock_path_operations
    mock_exists.return_value = False

    storage_error = StorageError(
        message="Access denied",
        retryable=False,
    )
    mock_extraction_storage.download_file.side_effect = storage_error

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=1,
        document_status=DocumentStatus.failed,
        temp_filename=None,
        error_trace="S3 Storage Error: Access denied",
    )

    mock_extract.assert_not_called()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_publisher.assert_not_called()


@pytest.mark.asyncio
async def test_execute_retryable_s3_error_propagates_without_marking_failed(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    extraction_document,
    mock_extraction_storage,
) -> None:
    mock_exists, mock_unlink = mock_path_operations
    mock_exists.return_value = False

    storage_error = S3ConnectionError(
        message="S3 temporarily unavailable",
        operation="download_file",
    )
    mock_extraction_storage.download_file.side_effect = storage_error

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        with pytest.raises(S3ConnectionError) as exc_info:
            await task.execute()

    assert exc_info.value is storage_error

    mock_extraction_storage.download_file.assert_awaited_once_with(
        FILE_KEY,
        task.temp_path,
    )

    assert not any(
        awaited_call.kwargs.get("document_status") == DocumentStatus.failed
        for awaited_call in mock_worker_repo.update_document_fields.await_args_list
    )

    mock_extract.assert_not_called()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_publisher.assert_not_called()
    mock_unlink.assert_not_called()


@pytest.mark.parametrize(
    "document_status",
    [
        DocumentStatus.failed,
        DocumentStatus.infected,
    ],
)
@pytest.mark.asyncio
async def test_execute_terminal_document_does_not_restart_extraction(
    document_status,
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_path_operations,
    mock_extraction_storage,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=document_status,
        file_key=FILE_KEY,
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extract.assert_not_called()
    mock_extraction_storage.download_file.assert_not_awaited()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.parametrize(
    "document_status",
    [
        DocumentStatus.created,
        DocumentStatus.scanning,
        DocumentStatus.uploading,
    ],
)
@pytest.mark.asyncio
async def test_execute_wrong_pipeline_status_does_not_start_extraction(
    document_status,
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_path_operations,
    mock_extraction_storage,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=document_status,
        file_key=FILE_KEY,
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extract.assert_not_called()
    mock_extraction_storage.download_file.assert_not_awaited()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_unlink.assert_not_called()


@pytest.mark.asyncio
async def test_execute_already_extracted_skips_extraction_and_dispatches_analysis(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_analysis_repo_worker,
    mock_analysis_service_worker,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
    mock_extraction_storage,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.extracted,
        file_key=FILE_KEY,
    )

    with patch(
        "src.worker.extraction_tasks.TextExtractor.extract",
    ) as mock_extract:
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

    mock_extract.assert_not_called()
    mock_extraction_storage.download_file.assert_not_awaited()
    mock_mongo_repo.upsert_raw_text.assert_not_awaited()
    mock_worker_repo.update_document_fields.assert_not_awaited()

    mock_publisher.assert_called_once_with(
        analysis_id="mock-analysis-id",
        document_id=1,
        user_id=1,
        request_id="req-123",
    )

    mock_unlink.assert_called_once_with(missing_ok=True)
