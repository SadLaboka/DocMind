from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from src.core.enums import AnalysisStatus, LLMProvider, MimeType


@pytest.mark.asyncio
async def test_get_analyses_success(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
    analysis_content_factory,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="analysis_user",
        email="analysis_user@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="analysis.pdf",
        description="analysis list test",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="analysis-request",
    )
    mock_analysis_repo.get_analyses_by_document_id.return_value = [analysis]

    response = await client.get(
        f"/documents/{document['id']}/analyses/",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["has_next"] is False

    assert len(data["analyses"]) == 1

    returned_analysis = data["analyses"][0]
    assert returned_analysis["id"] == analysis.id
    assert returned_analysis["provider"] == analysis.provider.value
    assert returned_analysis["status"] == analysis.status.value
    assert returned_analysis["retry_of_analysis_id"] is None


@pytest.mark.asyncio
async def test_get_analyses_parses_status_and_provider_filters(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="filtered_analysis_user",
        email="filtered_analysis_user@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="filtered.pdf",
        description="filter test",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    mock_analysis_repo.get_analyses_by_document_id.return_value = []

    response = await client.get(
        f"/documents/{document['id']}/analyses/",
        params=[
            ("page", "2"),
            ("limit", "5"),
            ("statuses", AnalysisStatus.success.value),
            ("statuses", AnalysisStatus.failed.value),
            ("providers", LLMProvider.gemini.value),
            ("providers", LLMProvider.deepseek.value),
        ],
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["analyses"] == []
    assert data["page"] == 2
    assert data["limit"] == 5
    assert data["has_next"] is False

    mock_analysis_repo.get_analyses_by_document_id.assert_awaited_once_with(
        document["id"],
        limit=6,
        skip=5,
        statuses=[
            AnalysisStatus.success,
            AnalysisStatus.failed,
        ],
        providers=[
            LLMProvider.gemini,
            LLMProvider.deepseek,
        ],
    )


@pytest.mark.asyncio
async def test_get_analyses_returns_404_for_another_users_document(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    owner_tokens = await create_token_pair(
        login="analysis_owner",
        email="analysis_owner@test.com",
        password_hash=hashed_password,
    )

    other_tokens = await create_token_pair(
        login="analysis_other",
        email="analysis_other@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=owner_tokens["user_id"],
        filename="private.pdf",
        description="private analysis",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    response = await client.get(
        f"/documents/{document['id']}/analyses/",
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"

    mock_analysis_repo.get_analyses_by_document_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_analyses_unauthorized(
    client: AsyncClient,
) -> None:
    response = await client.get("/documents/1/analyses/")

    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "limit=0",
        "limit=21",
        "statuses=unknown",
        "providers=unknown",
    ],
)
async def test_get_analyses_rejects_invalid_query_parameters(
    client: AsyncClient,
    create_token_pair,
    test_password,
    query: str,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="validation_user",
        email="validation@test.com",
        password_hash=hashed_password,
    )

    response = await client.get(
        f"/documents/1/analyses/?{query}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
