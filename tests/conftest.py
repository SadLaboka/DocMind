import pytest
import pytest_asyncio

from httpx import AsyncClient, ASGITransport

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
)

from main import app
from src.core.database import get_session
from src.core.config import settings
from src.core.security import get_password_hash


TEST_DB_URL = settings.db.url


@pytest_asyncio.fixture(scope="function")
async def db_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        echo=False,
        future=True,
    )

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_db_session(db_engine):
    async with db_engine.connect() as conn:
        transaction = await conn.begin()

        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
        )

        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session):
    async def override_get_session():
        yield test_db_session

    app.dependency_overrides[get_session] = override_get_session

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def create_user():
    async def _create(
        session: AsyncSession,
        login: str,
        email: str,
        password_hash: str,
    ):
        from src.models.users import User

        user = User(
            login=login,
            email=email,
            password_hash=password_hash,
            is_verified=False,
            is_admin=False,
            is_active=True,
            failed_login_attempts=0,
        )

        session.add(user)

        await session.flush()
        await session.refresh(user)

        return {
            "id": user.id,
            "login": user.login,
            "email": user.email,
        }

    return _create


@pytest.fixture
def test_password():
    plain = "SecureTestPass123!"
    return plain, get_password_hash(plain)