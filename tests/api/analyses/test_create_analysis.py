from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.core.enums import AnalysisStatus, DocumentStatus, LLMProvider, MimeType
from src.events.publisher import publish_document_analysis_requested


@pytest.mark.asyncio
async def test_create_analysis_success_with_explicit_provider(
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
        login="create_analysis_user",
        email="create_analysis_user@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="analysis.txt",
        description="create analysis test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for analysis",
    )

    request_id = "create-analysis-request"

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id=request_id,
    ).model_copy(
        update={"provider": LLMProvider.gemini},
    )
    mock_analysis_repo.create_analysis.return_value = analysis

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
            f"/documents/{document['id']}/analyses/",
            json={"provider": LLMProvider.gemini.value},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == analysis.id
    assert data["status"] == AnalysisStatus.queued.value
    assert data["provider"] == LLMProvider.gemini.value

    mock_analysis_repo.create_analysis.assert_awaited_once_with(
        document["id"],
        request_id,
        LLMProvider.gemini,
    )

    mock_to_thread.assert_awaited_once_with(
        publish_document_analysis_requested,
        analysis_id=str(analysis.id),
        document_id=document["id"],
        user_id=tokens["user_id"],
        request_id=request_id,
    )


@pytest.mark.asyncio
async def test_create_analysis_without_body_uses_default_provider(
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
        login="create_default_analysis",
        email="create_default_analysis@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="default.txt",
        description="default provider test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for analysis",
    )

    request_id = "default-provider-request"
    default_provider = LLMProvider(settings.llm.default_provider)

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id=request_id,
    ).model_copy(
        update={"provider": default_provider},
    )
    mock_analysis_repo.create_analysis.return_value = analysis

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
            f"/documents/{document['id']}/analyses/",
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 201
    assert response.json()["provider"] == default_provider.value

    mock_analysis_repo.create_analysis.assert_awaited_once_with(
        document["id"],
        request_id,
        default_provider,
    )

    mock_to_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_analysis_returns_404_for_another_users_document(
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
        login="create_analysis_owner",
        email="create_analysis_owner@test.com",
        password_hash=hashed_password,
    )
    other_tokens = await create_token_pair(
        login="create_analysis_other",
        email="create_analysis_other@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=owner_tokens["user_id"],
        filename="private.txt",
        description="private document",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    response = await client.post(
        f"/documents/{document['id']}/analyses/",
        json={"provider": LLMProvider.gemini.value},
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"

    mock_mongo_repo.get_content.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_analysis_returns_409_when_document_not_ready(
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
        login="create_analysis_not_ready",
        email="create_analysis_not_ready@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="pending.txt",
        description="pending document",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.uploaded,
    )

    response = await client.post(
        f"/documents/{document['id']}/analyses/",
        json={"provider": LLMProvider.gemini.value},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "document_not_ready_for_analysis"

    mock_mongo_repo.get_content.assert_not_awaited()
    mock_analysis_repo.create_analysis.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_analysis_rejects_invalid_provider(
    client: AsyncClient,
    create_token_pair,
    test_password,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="create_analysis_vld",
        email="create_analysis_validation@test.com",
        password_hash=hashed_password,
    )

    response = await client.post(
        "/documents/1/analyses/",
        json={"provider": "unknown-provider"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_analysis_returns_503_when_dispatch_fails(
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
        login="create_anls_dsptch_fail",
        email="create_analysis_dispatch_failure@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="dispatch.txt",
        description="dispatch failure test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    mock_mongo_repo.get_content.return_value = mongo_content_factory(
        document_id=document["id"],
        raw_text="ready for analysis",
    )

    request_id = "dispatch-failure-request"

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id=request_id,
    ).model_copy(
        update={"provider": LLMProvider.gemini},
    )
    mock_analysis_repo.create_analysis.return_value = analysis
    mock_analysis_repo.get_analysis_by_document_and_request.return_value = analysis

    primary_error = RuntimeError("RabbitMQ unavailable")

    with (
        patch(
            "src.core.middlewares.request_context.uuid4",
            return_value=request_id,
        ),
        patch(
            "src.services.analysis.asyncio.to_thread",
            new_callable=AsyncMock,
            side_effect=primary_error,
        ),
    ):
        response = await client.post(
            f"/documents/{document['id']}/analyses/",
            json={"provider": LLMProvider.gemini.value},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 503
    assert response.json()["code"] == "analysis_dispatch_failed"
