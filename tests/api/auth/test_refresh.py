import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_refresh_token_success(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="refresh_user", email="refresh@test.com", password_hash=hashed_pw)

    response = await client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_token_expired(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="expired_user", email="expired@test.com", password_hash=hashed_pw, expired=True)

    response = await client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401
    data = response.json()
    assert data.get("code") or data.get("detail")


@pytest.mark.asyncio
async def test_refresh_token_missing(client: AsyncClient):
    response = await client.post("/auth/refresh")

    assert response.status_code == 401
    data = response.json()
    assert data.get("code") == "invalid_credentials"


@pytest.mark.asyncio
async def test_refresh_token_wrong_type(client: AsyncClient, create_token_pair, test_password):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="wrong_type_user", email="type@test.com", password_hash=hashed_pw)

    response = await client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code in (401, 422)
    data = response.json()
    assert data.get("code") or data.get("detail")
