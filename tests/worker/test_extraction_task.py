from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.enums import DocumentStatus
from src.core.exceptions import ExtractionError
from src.worker.extraction_tasks import DocumentExtractionTask

# FIXTURES


@pytest.fixture
def mock_celery_session():
    with patch("src.worker.base_task.celery_session_factory") as mock_factory:
        mock_session = AsyncMock()
        mock_factory.return_value.__aenter__.return_value = mock_session
        yield mock_session, mock_factory


@pytest.fixture
def mock_repo():
    with (
        patch("src.worker.base_task.DocumentRepository") as mock_base,
        patch("src.worker.extraction_tasks.DocumentRepository") as mock_extraction,
    ):
        mock_instance = AsyncMock()
        mock_base.return_value = mock_instance
        mock_extraction.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_mongo_repo():
    with patch("src.worker.extraction_tasks.MongoDocumentRepository") as mock_repo_class:
        mock_instance = AsyncMock()
        mock_repo_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_init_mongo():
    with patch("src.worker.extraction_tasks.init_mongo_for_worker") as mock_init:
        mock_init.return_value = None
        yield mock_init


@pytest.fixture
def mock_publisher():
    with patch("src.worker.extraction_tasks.publish_document_text_extracted") as mock_pub:
        yield mock_pub


@pytest.fixture
def mock_path_operations():
    with (
        patch("pathlib.Path.exists", return_value=True) as mock_exists,
        patch("pathlib.Path.unlink") as mock_unlink,
    ):
        yield mock_exists, mock_unlink


# TESTS


@pytest.mark.asyncio
async def test_execute_success(
    mock_celery_session, mock_repo, mock_mongo_repo, mock_init_mongo, mock_publisher, mock_path_operations
):
    _, mock_unlink = mock_path_operations

    with patch("src.worker.extraction_tasks.TextExtractor.extract", return_value="Mocked extracted text"):
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            user_id=1,
            mime_type="text/plain",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

        mock_mongo_repo.create_content.assert_called_once_with(
            document_id=1,
            raw_text="Mocked extracted text",
        )

        mock_repo.update_document_fields.assert_any_call(
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
    mock_celery_session, mock_mongo_repo, mock_init_mongo, mock_repo, mock_path_operations
):
    _, mock_unlink = mock_path_operations

    mock_repo.get_document_by_id.return_value = MagicMock(document_status=DocumentStatus.cancelled)

    with patch("src.worker.extraction_tasks.TextExtractor.extract") as mock_extract:
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

        mock_repo.update_document_fields.assert_not_called()

        mock_mongo_repo.create_content.assert_not_called()


@pytest.mark.asyncio
async def test_process_extraction_hard_fail(
    mock_celery_session, mock_repo, mock_mongo_repo, mock_init_mongo, mock_path_operations
):
    _, mock_unlink = mock_path_operations

    mock_error = ExtractionError(error_code="invalid_file", log_context={"detail": "bad pdf structure"})

    with patch("src.worker.extraction_tasks.TextExtractor.extract", side_effect=mock_error):
        task = DocumentExtractionTask(
            document_id=1,
            temp_path="/tmp/bad.pdf",
            user_id=1,
            mime_type="application/pdf",
            request_id="req-123",
            provider="gemini",
        )

        await task.execute()

        mock_repo.update_document_fields.assert_called_with(
            document_id=1,
            document_status=DocumentStatus.failed,
            error_trace="{'detail': 'bad pdf structure'}",
            temp_filename=None,
        )

        mock_mongo_repo.create_content.assert_not_called()
        mock_unlink.assert_called_with(missing_ok=True)


@pytest.mark.asyncio
async def test_process_extraction_soft_fail(
    mock_celery_session, mock_repo, mock_mongo_repo, mock_init_mongo, mock_path_operations
):
    _, mock_unlink = mock_path_operations

    with patch("src.worker.extraction_tasks.TextExtractor.extract", side_effect=RuntimeError("Connection lost")):
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

        calls = [call[1] for call in mock_repo.update_document_fields.call_args_list]
        assert not any(call.get("document_status") == DocumentStatus.failed for call in calls)

        mock_unlink.assert_not_called()
        mock_mongo_repo.create_content.assert_not_called()


@pytest.mark.asyncio
async def test_update_status_after_failure(mock_celery_session, mock_repo):

    mock_repo.get_document_by_id.return_value = MagicMock(document_status=DocumentStatus.extracting)

    await DocumentExtractionTask._update_status_after_failure(
        document_id=1, error_detail="Task failed after 3 retries: Connection lost"
    )

    mock_repo.update_document_fields.assert_called_once_with(
        document_id=1,
        document_status=DocumentStatus.failed,
        error_trace="Task failed after all retries: Task failed after 3 retries: Connection lost",
    )
