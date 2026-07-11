from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

from src.core.exceptions import ConflictError


def _make_mock_prompt(
    version: str = "v1.0.0",
    prompt_type: str = "document_analysis",
    content: str = "Analyze this: {text}",
    is_active: bool = True,
):
    mock = MagicMock()
    mock.version = version
    mock.prompt_type = prompt_type
    mock.content = content
    mock.is_active = is_active
    mock.created_at = datetime.now(UTC)
    mock.updated_at = datetime.now(UTC)
    return mock


@pytest.mark.asyncio
async def test_create_prompt_success(
    client: AsyncClient,
    create_admin_token_pair,
    mock_mongo_prompt_repository,
):
    tokens = await create_admin_token_pair()
    mock_mongo_prompt_repository.create_prompt.return_value = _make_mock_prompt()

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this: {text}",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["version"] == "v1.0.0"
    assert data["prompt_type"] == "document_analysis"
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_create_prompt_forbidden(
    client: AsyncClient,
    create_token_pair,
    test_password,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="regular", email="regular@test.com", password_hash=hashed_pw, is_admin=False)

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this: {text}",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 403
    assert response.json()["code"] == "user_is_not_admin"


@pytest.mark.asyncio
async def test_create_prompt_unauthorized(client: AsyncClient):
    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this: {text}",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"


@pytest.mark.asyncio
async def test_create_prompt_duplicate_version(
    client: AsyncClient,
    create_admin_token_pair,
    mock_mongo_prompt_repository,
):
    tokens = await create_admin_token_pair()
    mock_mongo_prompt_repository.create_prompt.side_effect = ConflictError(
        error_code="conflict", message="Prompt version already exists"
    )

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v1.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this: {text}",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


@pytest.mark.asyncio
async def test_create_prompt_invalid_version_format(
    client: AsyncClient,
    create_admin_token_pair,
):
    tokens = await create_admin_token_pair()

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "1.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this: {text}",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_missing_text_placeholder(
    client: AsyncClient,
    create_admin_token_pair,
):
    tokens = await create_admin_token_pair()

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "document_analysis",
            "content": "Analyze this document",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_empty_content(
    client: AsyncClient,
    create_admin_token_pair,
):
    tokens = await create_admin_token_pair()

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "document_analysis",
            "content": "",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_prompt_invalid_prompt_type(
    client: AsyncClient,
    create_admin_token_pair,
):
    tokens = await create_admin_token_pair()

    response = await client.post(
        "/admin/prompts",
        json={
            "version": "v2.0.0",
            "prompt_type": "nonexistent_type",
            "content": "Analyze this: {text}",
        },
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
