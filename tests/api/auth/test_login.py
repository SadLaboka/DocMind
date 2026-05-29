import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, create_user, test_db_session, test_password):
    plain_pw, hashed_pw = test_password
    await create_user(test_db_session, login="user_success", email="success@test.com", password_hash=hashed_pw)

    response = await client.post("/auth/login", json={
        "login": "user_success",
        "password": plain_pw
    })

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_login_invalid_password(client: AsyncClient, create_user, test_db_session, test_password):
    plain_pw, hashed_pw = test_password
    await create_user(test_db_session, login="user_invalid", email="invalid@test.com", password_hash=hashed_pw)

    response = await client.post("/auth/login", json={
        "login": "user_invalid",
        "password": "WrongPassword123!"
    })

    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_login_user_not_found(client: AsyncClient):
    response = await client.post("/auth/login", json={
        "login": "nonexistent_user",
        "password": "AnyPassword123!"
    })
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "invalid_credentials"


@pytest.mark.parametrize("payload, expected_field", [
    ({"login": "user"}, "password"),
    ({"password": "pass"}, "login"),
    ({}, "login"),
    ({"login": "", "password": "123"}, "login"),
])
@pytest.mark.asyncio
async def test_login_validation_errors(client: AsyncClient, payload, expected_field):
    response = await client.post("/auth/login", json=payload)
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "validation_error"
    assert isinstance(data["detail"], list)
    assert any(err["field"] == expected_field for err in data["detail"])


@pytest.mark.asyncio
async def test_refresh_success(client: AsyncClient, create_user, test_db_session, test_password):
    pass
