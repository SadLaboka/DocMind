from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from src.core.enums import MimeType


ANALYSIS_ID = "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_get_analysis_success(
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
        login="detail_user",
        email="detail_user@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="detail.pdf",
        description="analysis detail test",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="detail-request",
    )
    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = analysis

    response = await client.get(
        f"/documents/{document['id']}/analyses/{ANALYSIS_ID}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == analysis.id
    assert data["provider"] == analysis.provider.value
    assert data["status"] == analysis.status.value
    assert data["retry_of_analysis_id"] is None


@pytest.mark.asyncio
async def test_get_analysis_returns_404_when_analysis_not_in_document(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    tokens = await create_token_pair(
        login="detail_nf",
        email="detail_nf@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="not-found.pdf",
        description="analysis not found test",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = None

    response = await client.get(
        f"/documents/{document['id']}/analyses/{ANALYSIS_ID}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "analysis_not_found"


@pytest.mark.asyncio
async def test_get_analysis_returns_404_for_another_users_document(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    owner_tokens = await create_token_pair(
        login="detail_owner",
        email="detail_owner@test.com",
        password_hash=hashed_password,
    )
    other_tokens = await create_token_pair(
        login="detail_other",
        email="detail_other@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=owner_tokens["user_id"],
        filename="private.pdf",
        description="private document",
        mime_type=MimeType.pdf,
        file_size=1024,
    )

    response = await client.get(
        f"/documents/{document['id']}/analyses/{ANALYSIS_ID}",
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_analysis_unauthorized(
    client: AsyncClient,
) -> None:
    response = await client.get(
        f"/documents/1/analyses/{ANALYSIS_ID}",
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"
