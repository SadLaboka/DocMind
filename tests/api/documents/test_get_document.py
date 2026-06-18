from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.enums import MimeType


@pytest.mark.asyncio
async def test_get_document_success(
    client: AsyncClient, test_password, create_document, create_token_pair, test_db_session, mock_mongo_content
):
    _, hashed_pw = test_password

    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    document = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="success.pdf",
        description="total success",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=uuid4().hex,
    )

    response = await client.get(
        f"/documents/{document['id']}", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == document["id"]
    assert data["user_id"] == document["user_id"]
    assert data["filename"] == document["filename"]
    assert data["description"] == document["description"]
    assert data["mime_type"] == document["mime_type"].value
    assert data["file_size"] == document["file_size"]
    assert data["document_status"] == document["document_status"].value

    assert data["document_text"] == mock_mongo_content.raw_text
    assert data["analysis"] == mock_mongo_content.analysis
    assert data["analysis_version"] == mock_mongo_content.analysis_version
    assert "created_at" in data
    assert "updated_at" in data
    assert "temp_filename" not in data


@pytest.mark.asyncio
async def test_get_document_success_admin(
        client: AsyncClient,
        test_password,
        create_document,
        create_user,
        create_token_pair,
        test_db_session,
        mock_mongo_content
):
    _, hashed_pw = test_password

    admins_tokens = await create_token_pair(
        login="admin", email="admin@test.com", is_admin=True, password_hash=hashed_pw
    )
    document_owner = await create_user(
        session=test_db_session,
        login="documentOwner",
        email="document_owner@test.com",
        password_hash=hashed_pw,
    )

    document = await create_document(
        session=test_db_session,
        user_id=document_owner["id"],
        filename="success.pdf",
        description="total success",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=uuid4().hex,
    )

    response = await client.get(
        f"/documents/{document['id']}", headers={"Authorization": f"Bearer {admins_tokens['access_token']}"}
    )

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == document["id"]
    assert data["user_id"] == document["user_id"]
    assert data["filename"] == document["filename"]
    assert data["description"] == document["description"]
    assert data["mime_type"] == document["mime_type"].value
    assert data["file_size"] == document["file_size"]
    assert data["document_status"] == document["document_status"].value

    assert data["document_text"] == mock_mongo_content.raw_text
    assert data["analysis"] == mock_mongo_content.analysis
    assert data["analysis_version"] == mock_mongo_content.analysis_version
    assert "created_at" in data
    assert "updated_at" in data
    assert "temp_filename" not in data


@pytest.mark.asyncio
async def test_get_document_unauthorized(client: AsyncClient):
    response = await client.get("/documents/1")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_document_forbidden(
    client: AsyncClient, create_document, create_token_pair, test_password, test_db_session
):
    _, hashed_pw = test_password

    tokens1 = await create_token_pair(login="user1", email="user1@test.com", password_hash=hashed_pw)
    document = await create_document(
        session=test_db_session,
        user_id=tokens1["user_id"],
        filename="forbidden.pdf",
        description="text for test",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=uuid4().hex,
    )

    tokens2 = await create_token_pair(login="user2", email="user2@test.com", password_hash=hashed_pw)
    response = await client.get(
        f"/documents/{document['id']}", headers={"Authorization": f"Bearer {tokens2['access_token']}"}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_not_found(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    response = await client.get("/documents/999999", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 404
