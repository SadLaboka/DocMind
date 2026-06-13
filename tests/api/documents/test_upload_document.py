import hashlib
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.core.enums import DocumentStatus, MimeType
from tests.conftest import FIXTURES_DIR

# SUCCESS CASES


@pytest.mark.asyncio
async def test_upload_document_success_new_file(client: AsyncClient, create_token_pair, test_password, test_db_session):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    test_file_path = FIXTURES_DIR / "documents" / "test.txt"
    test_file_bytes = test_file_path.read_bytes()

    with patch("src.services.file_processor.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = AsyncMock(id="fake-task-id")

        files = {"file": ("test.txt", test_file_bytes, "text/plain")}
        response = await client.post(
            "/documents/",
            files=files,
            data={"description": "New unique file"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 201
    resp_data = response.json()
    assert resp_data["filename"] == "test.txt"
    assert resp_data["document_status"] == DocumentStatus.created.value
    mock_to_thread.assert_called_once()


@pytest.mark.asyncio
async def test_upload_document_duplicate_fast_path(
    client: AsyncClient, create_token_pair, create_document, test_password, test_db_session
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    test_file_path = FIXTURES_DIR / "documents" / "test.txt"
    test_file_bytes = test_file_path.read_bytes()
    file_hash = hashlib.sha256(test_file_bytes).hexdigest()

    await create_document(
        session=test_db_session,
        user_id=tokens["user_id"],
        filename="test.txt",
        description="First upload",
        mime_type=MimeType.txt,
        file_size=len(test_file_bytes),
        temp_filename=None,
        document_status=DocumentStatus.extracted,
        document_text="Mocked extracted text from first run",
        file_hash=file_hash,
    )

    with patch("src.services.file_processor.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = AsyncMock(id="fake-task-id-2")

        files = {"file": ("test.txt", test_file_bytes, "text/plain")}
        response = await client.post(
            "/documents/",
            files=files,
            data={"description": "Duplicate upload"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 201
    resp_data = response.json()

    assert isinstance(resp_data["id"], int)
    assert resp_data["document_status"] == DocumentStatus.extracted.value
    assert resp_data["document_text"] == "Mocked extracted text from first run"

    mock_to_thread.assert_not_called()


# AUTHORIZATION & VALIDATION CASES


@pytest.mark.asyncio
async def test_upload_document_unauthorized(client: AsyncClient):
    test_file_path = FIXTURES_DIR / "documents" / "test.txt"
    test_file_bytes = test_file_path.read_bytes()

    files = {"file": ("test.txt", test_file_bytes, "text/plain")}
    response = await client.post(
        "/documents/",
        files=files,
        data={"description": "No auth"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid authentication credentials"


@pytest.mark.asyncio
async def test_upload_document_validation_missing_file(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    response = await client.post(
        "/documents/",
        data={"description": "No file attached"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_upload_document_validation_description_too_long(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    test_file_path = FIXTURES_DIR / "documents" / "test.txt"
    test_file_bytes = test_file_path.read_bytes()

    files = {"file": ("test.txt", test_file_bytes, "text/plain")}
    response = await client.post(
        "/documents/",
        files=files,
        data={"description": "x" * 301},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.asyncio
async def test_upload_document_file_empty(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    files = {"file": ("empty.txt", b"", "text/plain")}
    response = await client.post(
        "/documents/",
        files=files,
        data={"description": "Empty file"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "file_size_is_invalid"
    assert response.json()["detail"] == "The uploaded file is empty"


@pytest.mark.asyncio
async def test_upload_document_file_too_big(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    with patch("src.services.file_processor.UploadService._validate_size", return_value=None):
        files = {"file": ("big.txt", b"fake large content", "text/plain")}
        response = await client.post(
            "/documents/",
            files=files,
            data={"description": "Too big file"},
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "file_size_is_invalid"
    assert response.json()["detail"] == "The uploaded file is too big"


@pytest.mark.asyncio
async def test_upload_document_invalid_mime_type(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    files = {"file": ("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", "application/x-msdownload")}
    response = await client.post(
        "/documents/",
        files=files,
        data={"description": "Invalid type"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 400
    assert response.json()["code"] == "mime_type_is_invalid"
    assert "invalid type" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_document_missing_filename(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="uploader", email="up@test.com", password_hash=hashed_pw)

    files = {"file": ("", b"some content", "text/plain")}
    response = await client.post(
        "/documents/",
        files=files,
        data={"description": "No filename"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
