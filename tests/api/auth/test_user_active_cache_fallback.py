import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_fallback_to_db_user_active(
    client: AsyncClient,
    create_token_pair,
    test_password,
    mock_user_active_cache,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(
        login="fallback_active",
        email="fallback_active@test.com",
        password_hash=hashed_pw,
    )

    mock_user_active_cache.get_active.return_value = None

    response = await client.get(
        "/documents/",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 200
    mock_user_active_cache.set_active.assert_called_once()


@pytest.mark.asyncio
async def test_fallback_to_db_user_deactivated(
    client: AsyncClient,
    create_token_pair,
    test_password,
    mock_user_active_cache,
    test_db_session,
):
    _, hashed_pw = test_password
    tokens = await create_token_pair(
        login="fallback_deactivated",
        email="fallback_deactivated@test.com",
        password_hash=hashed_pw,
    )

    from sqlalchemy import update

    from src.models.users import User

    await test_db_session.execute(update(User).where(User.id == tokens["user_id"]).values(is_active=False))
    await test_db_session.commit()

    mock_user_active_cache.get_active.return_value = None

    response = await client.get(
        "/documents/",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == "user_deactivated"
