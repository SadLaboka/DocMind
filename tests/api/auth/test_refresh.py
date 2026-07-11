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
    tokens = await create_token_pair(
        login="expired_user", email="expired@test.com", password_hash=hashed_pw, expired=True
    )

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


@pytest.mark.asyncio
async def test_refresh_token_blacklisted(
    client: AsyncClient,
    create_token_pair,
    test_password,
    mock_token_blacklist,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(login="blacklisted_user", email="blacklisted@test.com", password_hash=hashed_pw)

    mock_token_blacklist.is_blacklisted.return_value = True

    response = await client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "token_revoked"


@pytest.mark.asyncio
async def test_refresh_deactivated_user(
    client: AsyncClient,
    create_user,
    test_db_session,
    test_password,
    mock_user_active_cache,
):
    _, hashed_pw = test_password
    user = await create_user(
        session=test_db_session,
        login="refresh_deactivated",
        email="refresh_deactivated@test.com",
        password_hash=hashed_pw,
    )
    from sqlalchemy import update

    from src.models.users import User

    await test_db_session.execute(update(User).where(User.id == user["id"]).values(is_active=False))
    await test_db_session.commit()

    mock_user_active_cache.get_active.return_value = False

    from datetime import UTC, datetime, timedelta

    import jwt

    from tests.conftest import get_test_jwt_manager

    jwt_mgr = get_test_jwt_manager()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user["id"]),
        "login": user["login"],
        "is_admin": False,
    }
    refresh_payload = {**payload, "type": "refresh", "exp": now + timedelta(days=7)}
    refresh_token = jwt.encode(refresh_payload, jwt_mgr.private_key, algorithm=jwt_mgr.algorithm)

    response = await client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "user_deactivated"
