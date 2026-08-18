from unittest.mock import AsyncMock, patch

from src.worker.base_task import BaseTask


def test_cleanup_file_does_not_raise_when_unlink_fails(
    mock_path_operations,
) -> None:
    _, mock_unlink = mock_path_operations
    mock_unlink.side_effect = PermissionError("Permission denied")

    task = BaseTask(
        document_id=1,
        temp_path="/tmp/test.txt",
        mime_type="text/plain",
        user_id=2,
        request_id="req-123",
        provider="gemini",
    )

    task._cleanup_file()

    mock_unlink.assert_called_once_with(missing_ok=True)


def test_on_task_failure_attempts_cleanup_when_status_recovery_fails(
    mock_path_operations,
) -> None:
    _, mock_unlink = mock_path_operations

    recovery_error = RuntimeError("PostgreSQL unavailable")
    mock_update_status = AsyncMock(side_effect=recovery_error)

    primary_error = RuntimeError("Task failed")

    with patch.object(
        BaseTask,
        "_update_status_after_failure",
        mock_update_status,
    ):
        BaseTask._on_task_failure(
            exc=primary_error,
            task_id="task-123",
            args=(),
            kwargs={
                "document_id": 1,
                "temp_path": "/tmp/test.txt",
                "user_id": 2,
            },
            _einfo=None,
        )

    mock_update_status.assert_awaited_once_with(
        1,
        str(primary_error),
    )
    mock_unlink.assert_called_once_with(missing_ok=True)


def test_on_task_failure_does_not_raise_when_cleanup_fails(
    mock_path_operations,
) -> None:
    _, mock_unlink = mock_path_operations
    mock_unlink.side_effect = OSError("Cannot remove temp file")

    mock_update_status = AsyncMock()
    primary_error = RuntimeError("Task failed")

    with patch.object(
        BaseTask,
        "_update_status_after_failure",
        mock_update_status,
    ):
        BaseTask._on_task_failure(
            exc=primary_error,
            task_id="task-123",
            args=(),
            kwargs={
                "document_id": 1,
                "temp_path": "/tmp/test.txt",
                "user_id": 2,
            },
            _einfo=None,
        )

    mock_update_status.assert_awaited_once_with(
        1,
        str(primary_error),
    )
    mock_unlink.assert_called_once_with(missing_ok=True)
