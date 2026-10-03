from unittest.mock import AsyncMock

import pytest
from beanie import BeanieObjectId
from httpx import AsyncClient

from src.core.enums import AnalysisStatus, DocumentStatus, LLMProvider, MimeType


ANALYSIS_ID = "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_remove_analysis_success(
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
        login="remove_analysis",
        email="remove_analysis@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="remove.txt",
        description="remove analysis test",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    analysis_id = BeanieObjectId(ANALYSIS_ID)

    analysis = analysis_content_factory(
        document_id=document["id"],
        request_id="analysis-request",
    ).model_copy(
        update={
            "id": analysis_id,
            "status": AnalysisStatus.success,
            "provider": LLMProvider.gemini,
        }
    )

    mock_analysis_repo.get_analysis_by_id_and_document_id.return_value = analysis
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.return_value = None
    mock_analysis_repo.remove_analysis_by_id.return_value = True

    response = await client.delete(
        f"/documents/{document['id']}/analyses/{ANALYSIS_ID}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200

    data = response.json()

    assert data["id"] == str(analysis_id)
    assert data["status"] == AnalysisStatus.success.value
    assert data["provider"] == LLMProvider.gemini.value

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_awaited_once_with(
        analysis_id,
        document["id"],
    )
    mock_analysis_repo.remove_analysis_by_id.assert_awaited_once_with(
        analysis_id,
    )


@pytest.mark.asyncio
async def test_remove_analysis_returns_404_for_another_users_document(
    client: AsyncClient,
    create_token_pair,
    create_document,
    test_db_session,
    test_password,
    mock_analysis_repo: AsyncMock,
) -> None:
    _, hashed_password = test_password

    owner_tokens = await create_token_pair(
        login="remove_owner",
        email="remove_owner@test.com",
        password_hash=hashed_password,
    )
    other_tokens = await create_token_pair(
        login="remove_other",
        email="remove_other@test.com",
        password_hash=hashed_password,
    )

    document = await create_document(
        session=test_db_session,
        user_id=owner_tokens["user_id"],
        filename="private.txt",
        description="private analysis",
        mime_type=MimeType.txt,
        file_size=100,
        document_status=DocumentStatus.extracted,
    )

    response = await client.delete(
        f"/documents/{document['id']}/analyses/{ANALYSIS_ID}",
        headers={"Authorization": f"Bearer {other_tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"

    mock_analysis_repo.get_analysis_by_id_and_document_id.assert_not_awaited()
    mock_analysis_repo.get_analysis_by_retry_of_analysis_id.assert_not_awaited()
    mock_analysis_repo.remove_analysis_by_id.assert_not_awaited()
