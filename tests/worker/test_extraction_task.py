from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.enums import DocumentStatus
from src.core.exceptions import ExtractionError
from src.worker.extraction_tasks import DocumentExtractionTask


@pytest.fixture
def mock_mongo_repo():
    with patch(
        "src.worker.extraction_tasks.MongoDocumentRepository",
    ) as mock_repo_class:
        mock_instance = AsyncMock()
        mock_repo_class.return_value = mock_instance
        yield mock_instance


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
        "src.worker.extraction_tasks.publish_document_text_extracted",
    ) as mock_publish:
        yield mock_publish


@pytest.mark.asyncio
async def test_execute_success(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_publisher,
    mock_path_operations,
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

    mock_mongo_repo.create_content.assert_awaited_once_with(
        document_id=1,
        raw_text="Mocked extracted text",
    )

    mock_worker_repo.update_document_fields.assert_any_await(
        document_id=1,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )

    mock_publisher.assert_called_once_with(
        document_id=1,
        user_id=1,
        mime_type="text/plain",
        request_id="req-123",
        provider="gemini",
    )

    mock_unlink.assert_called_with(missing_ok=True)


@pytest.mark.asyncio
async def test_execute_document_already_cancelled(
    mock_celery_session,
    mock_mongo_repo,
    mock_init_mongo,
    mock_worker_repo,
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
    mock_mongo_repo.create_content.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_extraction_hard_fail(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_path_operations,
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

    mock_mongo_repo.create_content.assert_not_awaited()
    mock_unlink.assert_called_with(missing_ok=True)


@pytest.mark.asyncio
async def test_process_extraction_soft_fail(
    mock_celery_session,
    mock_worker_repo,
    mock_mongo_repo,
    mock_init_mongo,
    mock_path_operations,
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
    mock_mongo_repo.create_content.assert_not_awaited()


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
        error_detail="Task failed after 3 retries: Connection lost",
    )

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        document_id=1,
        document_status=DocumentStatus.failed,
        error_trace=(
            "Task failed after all retries: "
            "Task failed after 3 retries: Connection lost"
        ),
    )
