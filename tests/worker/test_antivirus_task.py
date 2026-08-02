from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.antivirus.exceptions import AntivirusUnavailableError
from src.antivirus.scanner import AntivirusScanner, ScanResult
from src.core.enums import DocumentStatus
from src.worker.antivirus_tasks import (
    DocumentScanTask,
    upload_document_task,
)


@pytest.fixture
def mock_antivirus_scanner() -> MagicMock:
    return MagicMock(spec=AntivirusScanner)


@pytest.fixture
def antivirus_task(
    mock_antivirus_scanner: MagicMock,
) -> DocumentScanTask:
    with patch(
        "src.worker.antivirus_tasks.AntivirusScanner",
        return_value=mock_antivirus_scanner,
    ):
        return DocumentScanTask(
            document_id=1,
            temp_path="/tmp/test.txt",
            mime_type="text/plain",
            user_id=2,
            request_id="req-123",
            provider="gemini",
        )


@pytest.fixture
def mock_upload_publisher():
    with patch(
        "src.worker.antivirus_tasks.asyncio.to_thread",
        new_callable=AsyncMock,
    ) as mock_to_thread:
        yield mock_to_thread


@pytest.mark.asyncio
async def test_execute_clean_file_updates_status_and_enqueues_upload(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_antivirus_scanner.scan_file.return_value = ScanResult(
        is_infected=False,
        signature=None,
        duration_ms=15.5,
    )

    await antivirus_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.scanning,
        ),
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.extracting,
        ),
    ]

    mock_antivirus_scanner.scan_file.assert_called_once_with(
        antivirus_task.temp_path,
    )

    mock_upload_publisher.assert_awaited_once_with(
        upload_document_task.delay,
        document_id=antivirus_task.document_id,
        temp_path=str(antivirus_task.temp_path),
        mime_type=antivirus_task.mime_type,
        user_id=antivirus_task.user_id,
        request_id=antivirus_task.request_id,
        provider=antivirus_task.provider,
    )

    mock_unlink.assert_not_called()


@pytest.mark.asyncio
async def test_execute_infected_file_marks_document_and_removes_file(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_antivirus_scanner.scan_file.return_value = ScanResult(
        is_infected=True,
        signature="Eicar-Test-Signature",
        duration_ms=18.7,
    )

    await antivirus_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.scanning,
        ),
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.infected,
            error_trace="Malware detected: Eicar-Test-Signature",
        ),
    ]

    mock_antivirus_scanner.scan_file.assert_called_once_with(
        antivirus_task.temp_path,
    )
    mock_unlink.assert_called_once_with(missing_ok=True)
    mock_upload_publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_unavailable_fail_closed_marks_failed(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    antivirus_task.fail_on_unavailable = True
    mock_antivirus_scanner.scan_file.side_effect = AntivirusUnavailableError(
        original_error=TimeoutError("ClamAV timeout"),
    )

    await antivirus_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.scanning,
        ),
        call(
            document_id=antivirus_task.document_id,
            document_status=DocumentStatus.failed,
            error_trace="Antivirus service unavailable",
        ),
    ]

    mock_unlink.assert_called_once_with(missing_ok=True)
    mock_upload_publisher.assert_not_awaited()


@pytest.mark.asyncio
async def test_execute_unavailable_fail_open_enqueues_upload(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    antivirus_task.fail_on_unavailable = False
    mock_antivirus_scanner.scan_file.side_effect = AntivirusUnavailableError(
        original_error=OSError("Connection refused"),
    )

    await antivirus_task.execute()

    assert mock_worker_repo.update_document_fields.await_args_list == [
        call(
            antivirus_task.document_id,
            document_status=DocumentStatus.scanning,
        ),
        call(
            document_id=antivirus_task.document_id,
            document_status=DocumentStatus.extracting,
        ),
    ]

    mock_upload_publisher.assert_awaited_once_with(
        upload_document_task.delay,
        document_id=antivirus_task.document_id,
        temp_path=str(antivirus_task.temp_path),
        mime_type=antivirus_task.mime_type,
        user_id=antivirus_task.user_id,
        request_id=antivirus_task.request_id,
        provider=antivirus_task.provider,
    )

    mock_unlink.assert_not_called()


@pytest.mark.asyncio
async def test_execute_cancelled_document_skips_scanning(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.cancelled,
    )

    await antivirus_task.execute()

    mock_antivirus_scanner.scan_file.assert_not_called()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_upload_publisher.assert_not_awaited()
    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_execute_missing_document_skips_scanning(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    _, mock_unlink = mock_path_operations

    mock_worker_repo.get_document_by_id.return_value = None

    await antivirus_task.execute()

    mock_antivirus_scanner.scan_file.assert_not_called()
    mock_worker_repo.update_document_fields.assert_not_awaited()
    mock_upload_publisher.assert_not_awaited()
    mock_unlink.assert_called_once_with(missing_ok=True)


@pytest.mark.asyncio
async def test_execute_missing_file_marks_document_cancelled(
    mock_celery_session,
    mock_worker_repo,
    mock_path_operations,
    mock_antivirus_scanner,
    antivirus_task,
    mock_upload_publisher,
) -> None:
    mock_exists, mock_unlink = mock_path_operations
    mock_exists.return_value = False

    await antivirus_task.execute()

    mock_worker_repo.update_document_fields.assert_awaited_once_with(
        antivirus_task.document_id,
        document_status=DocumentStatus.cancelled,
    )

    mock_antivirus_scanner.scan_file.assert_not_called()
    mock_upload_publisher.assert_not_awaited()
    mock_unlink.assert_not_called()
