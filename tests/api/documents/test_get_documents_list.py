from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.enums import MimeType


@pytest.mark.asyncio
async def test_get_documents_success(
    client: AsyncClient, test_password, create_document, create_token_pair, test_db_session
):
    _, hashed_pw = test_password

    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    for i in range(5):
        await create_document(
            session=test_db_session,
            user_id=tokens["user_id"],
            filename=f"doc_{i}.pdf",
            description=f"Document {i}",
            mime_type=MimeType.pdf,
            file_size=1024 * (i + 1),
            temp_filename=uuid4().hex,
        )

    response = await client.get("/documents/", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    assert response.status_code == 200
    data = response.json()

    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "limit" in data
    assert "has_next" in data

    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["total"] == 5
    assert data["has_next"] is False

    assert len(data["items"]) == 5

    for item in data["items"]:
        assert "id" in item
        assert "user_id" in item
        assert "filename" in item
        assert "mime_type" in item
        assert "file_size" in item
        assert "document_status" in item
        assert "created_at" in item
        assert "updated_at" in item
        assert "temp_filename" not in item


@pytest.mark.asyncio
async def test_get_documents_pagination(
    client: AsyncClient, test_password, create_document, create_token_pair, test_db_session
):
    _, hashed_pw = test_password

    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    for i in range(25):
        await create_document(
            session=test_db_session,
            user_id=tokens["user_id"],
            filename=f"doc_{i}.pdf",
            description=f"Document {i}",
            mime_type=MimeType.pdf,
            file_size=1024,
            temp_filename=uuid4().hex,
        )

    response = await client.get(
        "/documents/?page=1&limit=10", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["total"] == 25
    assert data["has_next"] is True

    response = await client.get(
        "/documents/?page=2&limit=10", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["page"] == 2
    assert data["has_next"] is True

    response = await client.get(
        "/documents/?page=3&limit=10", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 5
    assert data["page"] == 3
    assert data["has_next"] is False


@pytest.mark.asyncio
async def test_get_documents_empty(client: AsyncClient, test_password, create_token_pair):
    _, hashed_pw = test_password

    tokens = await create_token_pair(login="empty_user", email="empty@test.com", password_hash=hashed_pw)

    response = await client.get("/documents/", headers={"Authorization": f"Bearer {tokens['access_token']}"})

    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["limit"] == 20
    assert data["has_next"] is False


@pytest.mark.asyncio
async def test_get_documents_unauthorized(client: AsyncClient):
    response = await client.get("/documents/")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_documents_isolation(
    client: AsyncClient, test_password, create_document, create_token_pair, test_db_session
):
    _, hashed_pw = test_password

    tokens1 = await create_token_pair(login="user1", email="user1@test.com", password_hash=hashed_pw)
    tokens2 = await create_token_pair(login="user2", email="user2@test.com", password_hash=hashed_pw)

    for i in range(3):
        await create_document(
            session=test_db_session,
            user_id=tokens1["user_id"],
            filename=f"user1_doc_{i}.pdf",
            description="User 1 doc",
            mime_type=MimeType.pdf,
            file_size=1024,
            temp_filename=uuid4().hex,
        )

    for i in range(2):
        await create_document(
            session=test_db_session,
            user_id=tokens2["user_id"],
            filename=f"user2_doc_{i}.pdf",
            description="User 2 doc",
            mime_type=MimeType.pdf,
            file_size=1024,
            temp_filename=uuid4().hex,
        )

    response = await client.get("/documents/", headers={"Authorization": f"Bearer {tokens1['access_token']}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert all(item["filename"].startswith("user1_doc_") for item in data["items"])

    response = await client.get("/documents/", headers={"Authorization": f"Bearer {tokens2['access_token']}"})
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all(item["filename"].startswith("user2_doc_") for item in data["items"])


@pytest.mark.asyncio
async def test_get_documents_validation_page(client: AsyncClient, test_password, create_token_pair):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    response = await client.get("/documents/?page=0", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 422

    response = await client.get("/documents/?page=-1", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_documents_validation_limit(client: AsyncClient, test_password, create_token_pair):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    response = await client.get("/documents/?limit=0", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 422

    response = await client.get("/documents/?limit=51", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 422

    response = await client.get("/documents/?limit=1", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200

    response = await client.get("/documents/?limit=50", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_documents_field_values(
    client: AsyncClient, test_password, create_document, create_token_pair, test_db_session
):
    _, hashed_pw = test_password

    tokens = await create_token_pair(login="test_user", email="test@test.com", password_hash=hashed_pw)

    doc = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="exact_match.pdf",
        description="Exact test",
        mime_type=MimeType.txt,
        file_size=2048,
        temp_filename=uuid4().hex,
    )

    response = await client.get("/documents/", headers={"Authorization": f"Bearer {tokens['access_token']}"})
    assert response.status_code == 200
    data = response.json()

    item = data["items"][0]
    assert item["id"] == doc["id"]
    assert item["user_id"] == doc["user_id"]
    assert item["filename"] == doc["filename"]
    assert item["description"] == doc["description"]
    assert item["mime_type"] == doc["mime_type"].value
    assert item["file_size"] == doc["file_size"]
    assert item["document_status"] == doc["document_status"].value
    assert "created_at" in item
    assert "updated_at" in item
