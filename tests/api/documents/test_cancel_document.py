from pathlib import Path
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.config import settings
from src.core.enums import DocumentStatus, MimeType

# SUCCESS CASES


@pytest.mark.asyncio
async def test_cancel_document_by_owner(
    client: AsyncClient, create_token_pair, create_document, test_password, test_db_session
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="owner", email="owner@test.com", password_hash=hashed_pw)

    temp_file = uuid4().hex
    doc = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="to_cancel.pdf",
        description="Will be cancelled",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=temp_file,
    )

    temp_dir = Path(settings.base_dir).parent / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    test_file_path = temp_dir / temp_file
    test_file_path.touch()

    assert test_file_path.exists()

    response = await client.delete(
        f"/documents/{doc['id']}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["document_status"] == DocumentStatus.cancelled.value

    assert not test_file_path.exists()


@pytest.mark.asyncio
async def test_cancel_document_by_admin(
    client: AsyncClient, create_token_pair, create_user, create_document, test_password, test_db_session
):
    _, hashed_pw = test_password

    admin_tokens = await create_token_pair(
        login="admin", email="admin@test.com", is_admin=True, password_hash=hashed_pw
    )

    regular_user = await create_user(
        session=test_db_session,
        login="regular_user",
        email="regular@test.com",
        password_hash=hashed_pw,
    )

    doc = await create_document(
        session=test_db_session,
        user_id=regular_user["id"],
        filename="admin_cancel.pdf",
        description="Cancelled by admin",
        mime_type=MimeType.pdf,
        file_size=2048,
        temp_filename=uuid4().hex,
    )

    response = await client.delete(
        f"/documents/{doc['id']}",
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["document_status"] == DocumentStatus.cancelled.value


# AUTHORIZATION & PERMISSION CASES


@pytest.mark.asyncio
async def test_cancel_document_unauthorized(client: AsyncClient):
    response = await client.delete("/documents/1")

    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"


@pytest.mark.asyncio
async def test_cancel_document_forbidden(
    client: AsyncClient, create_token_pair, create_document, test_password, test_db_session
):
    _, hashed_pw = test_password

    tokens1 = await create_token_pair(login="user1", email="user1@test.com", password_hash=hashed_pw)
    tokens2 = await create_token_pair(login="user2", email="user2@test.com", password_hash=hashed_pw)

    doc = await create_document(
        session=test_db_session,
        user_id=tokens1["user_id"],
        filename="forbidden.pdf",
        description="Secret doc",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=uuid4().hex,
    )

    response = await client.delete(
        f"/documents/{doc['id']}",
        headers={"Authorization": f"Bearer {tokens2['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"


# EDGE CASES & IDEMPOTENCY


@pytest.mark.asyncio
async def test_cancel_document_idempotent(
    client: AsyncClient, create_token_pair, create_document, test_password, test_db_session
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="user", email="user@test.com", password_hash=hashed_pw)

    doc = await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="already_cancelled.pdf",
        description="Already cancelled",
        mime_type=MimeType.pdf,
        file_size=1024,
        temp_filename=None,
        document_status=DocumentStatus.cancelled,
    )

    response1 = await client.delete(
        f"/documents/{doc['id']}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response1.status_code == 200
    assert response1.json()["document_status"] == DocumentStatus.cancelled.value

    response2 = await client.delete(
        f"/documents/{doc['id']}",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response2.status_code == 200
    assert response2.json()["document_status"] == DocumentStatus.cancelled.value


@pytest.mark.asyncio
async def test_cancel_document_not_found(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="user", email="user@test.com", password_hash=hashed_pw)

    response = await client.delete(
        "/documents/999999",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "document_not_found"
