from unittest.mock import AsyncMock, patch

import pytest
from beanie import BeanieObjectId
from httpx import AsyncClient

from src.core.enums import AnalysisFailureKind, AnalysisStatus, DocumentStatus, LLMProvider, MimeType
from src.events.publisher import publish_document_analysis_requested


SOURCE_ANALYSIS_ID = "507f1f77bcf86cd799439011"
RETRY_ANALYSIS_ID = "507f1f77bcf86cd799439012"


@pytest.mark.asyncio
async def test_retry_analysis_success(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_mongo_repo: AsyncMock,
    mock_analysis_repo: AsyncMock,
    mongo_content_factory,
    analysis_content_factory,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="retry_user",
        email="retry_user@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="retry.txt",
        description="retry analysis test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for retry",
    )

    source_id = BeanieObjectId(SOURCE_ANALYSIS_ID)
    retry_id = BeanieObjectId(RETRY_ANALYSIS_ID)
    request_id = "retry-analysis-request"

    source_analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
            "provider": LLMProvider.gemini,
        }
    )
    retried_analysis = analysis_content_factory(
        document_id=document["id"],
        request_id=request_id,
    ).model_copy(
        update={
            "id": retry_id,
            "provider": LLMProvider.gemini,
            "retry_of_analysis_id": source_id,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.return_value = None
    mock_analysis_repo.create_analysis.return_value = retried_analysis

    with (
        patch(
            "src.core.middlewares.request_context.uuid4",
            return_value=request_id,
        ),
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
        ) as mock_to_thread,
    ):
        response = await client.post(
            f"/documents/{document['id']}/analyses/{SOURCE_ANALYSIS_ID}/retry",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == str(retry_id)
    assert data["status"] == AnalysisStatus.queued.value
    assert data["provider"] == LLMProvider.gemini.value
    assert data["retry_of_analysis_id"] == str(source_id)

    mock_analysis_repo.create_analysis.assert_awaited_once_with(
        document_id=document["id"],
        request_id=request_id,
        provider=LLMProvider.gemini,
        retry_of_analysis_id=source_id,
    )

    mock_to_thread.assert_awaited_once_with(
        publish_document_analysis_requested,
        analysis_id=str(retry_id),
        document_id=document["id"],
        user_id=tokens["user_id"],
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_retry_analysis_returns_404_for_another_users_document(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_mongo_repo: AsyncMock,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    owner_tokens = await create_token_pair(
        login="retry_owner",
        email="retry_owner@test.com",
        password_hash=hashed_password,
    )
    other_tokens = await create_token_pair(
        login="retry_other",
        email="retry_other@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=owner_tokens["user_id"],
        filename="private.txt",
        description="private retry test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    response = await client.post(
        f"/documents/{document['id']}/analyses/{SOURCE_ANALYSIS_ID}/retry",
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"

    mock_mongo_repo.get_content.assert_not_awaited()
    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_returns_409_when_document_not_ready(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_mongo_repo: AsyncMock,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="retry_not_ready",
        email="retry_not_ready@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="pending.txt",
        description="not ready retry test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.uploaded,
    )

    response = await client.post(
        f"/documents/{document['id']}/analyses/{SOURCE_ANALYSIS_ID}/retry",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "document_not_ready_for_analysis"

    mock_mongo_repo.get_content.assert_not_awaited()
    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_returns_409_when_analysis_not_retryable(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_mongo_repo: AsyncMock,
    mock_analysis_repo: AsyncMock,
    mongo_content_factory,
    analysis_content_factory,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="retry_nonretry",
        email="retry_nonretry@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="success.txt",
        description="non retryable analysis",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for analysis",
    )

    source_analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="source-request",
    ).model_copy(
        update={
            "id": BeanieObjectId(SOURCE_ANALYSIS_ID),
            "status": AnalysisStatus.success,
            "failure_kind": None,
        }
    )
    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis

    response = await client.post(
        f"/documents/{document['id']}/analyses/{SOURCE_ANALYSIS_ID}/retry",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "analysis_not_retryable"

    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_analysis_returns_409_when_analysis_already_retried(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_mongo_repo: AsyncMock,
    mock_analysis_repo: AsyncMock,
    mongo_content_factory,
    analysis_content_factory,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="retry_existing",
        email="retry_existing@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="retried.txt",
        description="already retried analysis",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for analysis",
    )

    source_id = BeanieObjectId(SOURCE_ANALYSIS_ID)

    source_analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="source-request",
    ).model_copy(
        update={
            "id": source_id,
            "status": AnalysisStatus.failed,
            "failure_kind": AnalysisFailureKind.transient,
        }
    )
    existing_retry = analysis_content_factory(
        document_id=document["id"],
        request_id="existing-retry",
    ).model_copy(
        update={
            "id": BeanieObjectId(RETRY_ANALYSIS_ID),
            "retry_of_analysis_id": source_id,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = source_analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.return_value = existing_retry

    response = await client.post(
        f"/documents/{document['id']}/analyses/{SOURCE_ANALYSIS_ID}/retry",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "analysis_already_retried"

    mock_analysis_repo.create_analysis.assert_not_awaited()
