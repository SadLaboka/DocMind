import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_logout_success(
    client: AsyncClient,
    create_token_pair,
    test_password,
    mock_token_blacklist,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="logout_user", email="logout@test.com", password_hash=hashed_pw)

    response = await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    assert response.json()["detail"] == "Successfully logged out"
    mock_token_blacklist.add_to_blacklist.assert_called_once()


@pytest.mark.asyncio
async def test_logout_unauthorized(client: AsyncClient):
    response = await client.post("/auth/logout")
    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"


@pytest.mark.asyncio
async def test_logout_revokes_token(
    client: AsyncClient,
    create_token_pair,
    test_password,
    mock_token_blacklist,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="revoke_user", email="revoke@test.com", password_hash=hashed_pw)

    await client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    mock_token_blacklist.is_blacklisted.return_value = True

    response = await client.get(
        "/documents/",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "token_revoked"
