from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import UploadFile
from pymongo.errors import ConnectionFailure

from src.core.config import settings
from src.core.enums import DocumentStatus, LLMProvider, MimeType
from src.services.file_processor import PreparedUpload, ProcessingPath, UploadService

pytestmark = pytest.mark.asyncio

USER_ID = 1
REQUEST_ID = "request-id"
DESCRIPTION = "unit test"


async def process_upload(
    service: UploadService,
    uploaded_file: UploadFile,
):
    return await service.process_upload(
        uploaded_file=uploaded_file,
        user_id=USER_ID,
        description=DESCRIPTION,
        request_id=REQUEST_ID,
        provider=LLMProvider.deepseek,
    )


async def test_analysis_only_connection_failure_degrades_to_extraction(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    mock_mongo_document_repository,
    document_factory,
):
    prepared_upload = PreparedUpload(
        path=ProcessingPath.ANALYSIS_ONLY,
        source_document_id=50,
        file_key="documents/reused-file",
        raw_text="reused text",
    )

    mock_mongo_document_repository.upsert_raw_text.side_effect = ConnectionFailure("Mongo unavailable")

    mock_document_repository.update_document_fields.return_value = document_factory(
        document_id=101,
        document_status=DocumentStatus.uploaded,
        temp_filename="unit-upload.txt",
        file_key="documents/reused-file",
    )

    celery_result = MagicMock()
    celery_result.id = "extract-task-id"

    mock_extract = AsyncMock(return_value=celery_result)
    mock_publish = AsyncMock()

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_extraction",
            new=mock_extract,
        ),
        patch.object(
            upload_service,
            "_publish_to_analysis",
            new=mock_publish,
        ),
    ):
        response = await process_upload(upload_service, uploaded_file)

    assert response.status == DocumentStatus.uploaded

    mock_mongo_document_repository.upsert_raw_text.assert_awaited_once_with(
        document_id=101,
        raw_text="reused text",
    )

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        document_status=DocumentStatus.uploaded,
        temp_filename="unit-upload.txt",
    )

    mock_extract.assert_awaited_once_with(
        document_id=101,
        temp_path=upload_temp_path,
        user_id=USER_ID,
        mime_type=MimeType.txt.value,
        request_id=REQUEST_ID,
        provider=LLMProvider.deepseek.value,
    )
    mock_publish.assert_not_awaited()

    assert upload_temp_path.exists()


async def test_analysis_only_unexpected_mongo_error_marks_document_failed_and_removes_temp(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    mock_mongo_document_repository,
):
    prepared_upload = PreparedUpload(
        path=ProcessingPath.ANALYSIS_ONLY,
        source_document_id=50,
        file_key="documents/reused-file",
        raw_text="reused text",
    )

    primary_error = RuntimeError("Unexpected Mongo error")
    mock_mongo_document_repository.upsert_raw_text.side_effect = primary_error

    mock_extract = AsyncMock()
    mock_publish = AsyncMock()

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_extraction",
            new=mock_extract,
        ),
        patch.object(
            upload_service,
            "_publish_to_analysis",
            new=mock_publish,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    mock_extract.assert_not_awaited()
    mock_publish.assert_not_awaited()

    assert not upload_temp_path.exists()


async def test_analysis_publish_failure_marks_document_failed_without_extraction(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    mock_mongo_document_repository,
):
    prepared_upload = PreparedUpload(
        path=ProcessingPath.ANALYSIS_ONLY,
        source_document_id=50,
        file_key="documents/reused-file",
        raw_text="reused text",
    )

    primary_error = RuntimeError("RabbitMQ publish failed")

    mock_extract = AsyncMock()
    mock_publish = AsyncMock(side_effect=primary_error)

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_extraction",
            new=mock_extract,
        ),
        patch.object(
            upload_service,
            "_publish_to_analysis",
            new=mock_publish,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_mongo_document_repository.upsert_raw_text.assert_awaited_once_with(
        document_id=101,
        raw_text="reused text",
    )

    mock_extract.assert_not_awaited()
    mock_publish.assert_awaited_once()

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    assert not upload_temp_path.exists()


async def test_full_pipeline_dispatch_failure_marks_document_failed_and_removes_temp(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    monkeypatch,
):
    monkeypatch.setattr(settings.antivirus, "enabled", True)

    prepared_upload = PreparedUpload(
        path=ProcessingPath.FULL_PIPELINE,
    )

    primary_error = RuntimeError("Scan dispatch failed")

    mock_scan = AsyncMock(side_effect=primary_error)
    mock_upload = AsyncMock()

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_scanning",
            new=mock_scan,
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_uploading",
            new=mock_upload,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_scan.assert_awaited_once()
    mock_upload.assert_not_awaited()

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    assert not upload_temp_path.exists()


async def test_extraction_only_dispatch_failure_marks_document_failed_and_removes_temp(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
):
    prepared_upload = PreparedUpload(
        path=ProcessingPath.EXTRACTION_ONLY,
        source_document_id=50,
        file_key="documents/reused-file",
    )

    primary_error = RuntimeError("Extraction dispatch failed")
    mock_extract = AsyncMock(side_effect=primary_error)

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_extraction",
            new=mock_extract,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_extract.assert_awaited_once()

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    assert not upload_temp_path.exists()


async def test_mark_failed_error_does_not_mask_primary_error_and_cleanup_still_runs(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    monkeypatch,
):
    monkeypatch.setattr(settings.antivirus, "enabled", True)

    prepared_upload = PreparedUpload(
        path=ProcessingPath.FULL_PIPELINE,
    )

    primary_error = RuntimeError("Dispatch failed")
    recovery_error = RuntimeError("PostgreSQL unavailable")

    mock_document_repository.update_document_fields.side_effect = recovery_error
    mock_scan = AsyncMock(side_effect=primary_error)

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_scanning",
            new=mock_scan,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    assert not upload_temp_path.exists()


async def test_cleanup_error_does_not_mask_primary_error(
    upload_service,
    uploaded_file,
    upload_temp_path,
    mock_document_repository,
    monkeypatch,
):
    monkeypatch.setattr(settings.antivirus, "enabled", True)

    prepared_upload = PreparedUpload(
        path=ProcessingPath.FULL_PIPELINE,
    )

    primary_error = RuntimeError("Dispatch failed")
    cleanup_error = PermissionError("Cannot remove temp file")

    mock_scan = AsyncMock(side_effect=primary_error)

    with (
        patch.object(
            upload_service,
            "_determine_processing_path",
            new=AsyncMock(return_value=prepared_upload),
        ),
        patch.object(
            upload_service,
            "_send_to_queue_for_scanning",
            new=mock_scan,
        ),
        patch.object(
            Path,
            "unlink",
            side_effect=cleanup_error,
        ),
        pytest.raises(RuntimeError) as exc_info,
    ):
        await process_upload(upload_service, uploaded_file)

    assert exc_info.value is primary_error

    mock_document_repository.update_document_fields.assert_awaited_once_with(
        document_id=101,
        temp_filename=None,
        document_status=DocumentStatus.failed,
        error_trace="Document processing failed",
    )

    assert upload_temp_path.exists()
