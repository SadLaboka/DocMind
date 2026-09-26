from unittest.mock import AsyncMock

import pytest
from pymongo.errors import ConnectionFailure

from src.core.enums import DocumentStatus
from src.core.exceptions import ConflictError
from src.schemas.users import User
from src.services.documents import DocumentService

pytestmark = pytest.mark.asyncio


async def test_ensure_ready_for_analysis_success(
    mock_document_repository: AsyncMock,
    mock_mongo_document_repository: AsyncMock,
    mock_analysis_repo: AsyncMock,
    document_factory,
    mongo_content_factory,
) -> None:
    user = User(
        id=7,
        login="unit-user",
        is_admin=False,
    )
    document = document_factory(
        document_id=42,
        user_id=user.id,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )
    content = mongo_content_factory(
        document_id=document.id,
        raw_text="extracted text",
    )

    mock_document_repository.get_document_by_id_and_user.return_value = document
    mock_mongo_document_repository.get_content.return_value = content

    service = DocumentService(
        repository=mock_document_repository,
        mongo_repository=mock_mongo_document_repository,
        analysis_repository=mock_analysis_repo,
    )

    await service.ensure_ready_for_analysis(user, document.id)

    mock_document_repository.get_document_by_id_and_user.assert_awaited_once_with(
        document.id,
        user.id,
    )
    mock_mongo_document_repository.get_content.assert_awaited_once_with(
        document.id,
    )


async def test_ensure_ready_for_analysis_rejects_non_extracted_document_without_mongo_lookup(
    mock_document_repository: AsyncMock,
    mock_mongo_document_repository: AsyncMock,
    mock_analysis_repo: AsyncMock,
    document_factory,
) -> None:
    user = User(
        id=7,
        login="unit-user",
        is_admin=False,
    )
    document = document_factory(
        document_id=42,
        user_id=user.id,
        document_status=DocumentStatus.uploaded,
    )

    mock_document_repository.get_document_by_id_and_user.return_value = document

    service = DocumentService(
        repository=mock_document_repository,
        mongo_repository=mock_mongo_document_repository,
        analysis_repository=mock_analysis_repo,
    )

    with pytest.raises(ConflictError) as exc_info:
        await service.ensure_ready_for_analysis(user, document.id)

    assert exc_info.value.error_code == "document_not_ready_for_analysis"

    mock_mongo_document_repository.get_content.assert_not_awaited()


async def test_ensure_ready_for_analysis_rejects_missing_raw_text(
    mock_document_repository: AsyncMock,
    mock_mongo_document_repository: AsyncMock,
    mock_analysis_repo: AsyncMock,
    document_factory,
    mongo_content_factory,
) -> None:
    user = User(
        id=7,
        login="unit-user",
        is_admin=False,
    )
    document = document_factory(
        document_id=42,
        user_id=user.id,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )
    content = mongo_content_factory(
        document_id=document.id,
        raw_text=None,
    )

    mock_document_repository.get_document_by_id_and_user.return_value = document
    mock_mongo_document_repository.get_content.return_value = content

    service = DocumentService(
        repository=mock_document_repository,
        mongo_repository=mock_mongo_document_repository,
        analysis_repository=mock_analysis_repo,
    )

    with pytest.raises(ConflictError) as exc_info:
        await service.ensure_ready_for_analysis(user, document.id)

    assert exc_info.value.error_code == "document_not_ready_for_analysis"

    mock_mongo_document_repository.get_content.assert_awaited_once_with(
        document.id,
    )


async def test_ensure_ready_for_analysis_propagates_mongo_failure(
    mock_document_repository: AsyncMock,
    mock_mongo_document_repository: AsyncMock,
    mock_analysis_repo: AsyncMock,
    document_factory,
) -> None:
    user = User(
        id=7,
        login="unit-user",
        is_admin=False,
    )
    document = document_factory(
        document_id=42,
        user_id=user.id,
        document_status=DocumentStatus.extracted,
        temp_filename=None,
    )

    mongo_error = ConnectionFailure("Mongo unavailable")

    mock_document_repository.get_document_by_id_and_user.return_value = document
    mock_mongo_document_repository.get_content.side_effect = mongo_error

    service = DocumentService(
        repository=mock_document_repository,
        mongo_repository=mock_mongo_document_repository,
        analysis_repository=mock_analysis_repo,
    )

    with pytest.raises(ConnectionFailure) as exc_info:
        await service.ensure_ready_for_analysis(user, document.id)

    assert exc_info.value is mongo_error
