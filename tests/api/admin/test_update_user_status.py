import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_update_user_status_success(
    client: AsyncClient,
    create_token_pair,
    create_user,
    test_password,
    test_db_session,
    mock_user_active_cache,
):
    _, hashed_pw = test_password
    admin_tokens = await create_token_pair(
        login="admin", email="admin@test.com", password_hash=hashed_pw, is_admin=True
    )
    regular_user = await create_user(
        session=test_db_session,
        login="regular_user",
        email="regular@test.com",
        password_hash=hashed_pw,
    )

    response = await client.patch(
        f"/admin/users/{regular_user['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_active"] is False
    mock_user_active_cache.set_active.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_status_forbidden(
    client: AsyncClient,
    create_token_pair,
    create_user,
    test_password,
    test_db_session,
):
    _, hashed_pw = test_password
    regular_tokens = await create_token_pair(
        login="regular", email="regular@test.com", password_hash=hashed_pw, is_admin=False
    )
    other_user = await create_user(
        session=test_db_session,
        login="other_user",
        email="other@test.com",
        password_hash=hashed_pw,
    )

    response = await client.patch(
        f"/admin/users/{other_user['id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {regular_tokens['access_token']}"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "user_is_not_admin"


@pytest.mark.asyncio
async def test_update_user_status_self_deactivation(
    client: AsyncClient,
    create_token_pair,
    test_password,
):
    _, hashed_pw = test_password
    admin_tokens = await create_token_pair(
        login="admin_self", email="admin_self@test.com", password_hash=hashed_pw, is_admin=True
    )

    response = await client.patch(
        f"/admin/users/{admin_tokens['user_id']}/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "cannot_deactivate_yourself"


@pytest.mark.asyncio
async def test_update_user_status_unauthorized(client: AsyncClient):
    response = await client.patch(
        "/admin/users/1/status",
        json={"is_active": False},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "No credentials provided"


@pytest.mark.asyncio
async def test_update_user_status_not_found(
    client: AsyncClient,
    create_token_pair,
    test_password,
):
    _, hashed_pw = test_password
    admin_tokens = await create_token_pair(
        login="admin_nf", email="admin_nf@test.com", password_hash=hashed_pw, is_admin=True
    )

    response = await client.patch(
        "/admin/users/999999/status",
        json={"is_active": False},
        headers={"Authorization": f"Bearer {admin_tokens['access_token']}"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"
