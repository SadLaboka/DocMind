import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "users/register", json={"login": "test", "email": "test@test.com", "password": "testpw1234"}
    )

    assert response.status_code == 201

    data = response.json()

    assert data["login"] == "test"
    assert data["email"] == "test@test.com"
    assert "id" in data
    assert isinstance(data["id"], int)
    assert data["id"] > 0


@pytest.mark.asyncio
async def test_register_validation_login_too_short(client: AsyncClient):
    response = await client.post(
        "/users/register", json={"login": "abc", "email": "test@test.com", "password": "securepass123"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_validation_login_too_long(client: AsyncClient):
    response = await client.post(
        "/users/register", json={"login": "a" * 26, "email": "test@test.com", "password": "securepass123"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_validation_invalid_email(client: AsyncClient):
    response = await client.post(
        "/users/register", json={"login": "validuser", "email": "not-an-email", "password": "securepass123"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_validation_password_too_short(client: AsyncClient):
    response = await client.post(
        "/users/register", json={"login": "validuser", "email": "test@test.com", "password": "123"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_validation_password_too_long(client: AsyncClient):
    response = await client.post(
        "/users/register", json={"login": "validuser", "email": "test@test.com", "password": "a" * 65}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_register_duplicate_login(client: AsyncClient, create_user, test_db_session, test_password):
    _, hashed_pw = test_password
    await create_user(session=test_db_session, login="duplicate_login", email="first@test.com", password_hash=hashed_pw)

    response = await client.post(
        "/users/register", json={"login": "duplicate_login", "email": "second@test.com", "password": "securepass123"}
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, create_user, test_db_session, test_password):
    _, hashed_pw = test_password
    await create_user(
        session=test_db_session, login="first_user", email="duplicate_email@test.com", password_hash=hashed_pw
    )

    response = await client.post(
        "/users/register",
        json={"login": "second_user", "email": "duplicate_email@test.com", "password": "securepass123"},
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_missing_fields(client: AsyncClient):
    response = await client.post("/users/register", json={"login": "testuser"})
    assert response.status_code == 422
