from datetime import UTC
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from main import app
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from src.core.config import settings
from src.core.database import get_session
from src.core.enums import MimeType
from src.core.jwt import JWTManager
from src.core.security import get_password_hash
from src.DependencyInjection.auth import get_jwt_manager

TEST_DB_URL = settings.db.url
FIXTURES_DIR = Path(__file__).parent / "fixtures"


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
            if transaction.is_active:
                await transaction.rollback()


@pytest_asyncio.fixture(scope="function")
async def client(test_db_session):
    async def override_get_session():
        yield test_db_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_manager] = get_test_jwt_manager

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
        is_admin: bool = False,
    ):
        from src.models.users import User

        user = User(
            login=login,
            email=email,
            password_hash=password_hash,
            is_verified=False,
            is_admin=is_admin,
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


@pytest_asyncio.fixture(scope="function")
async def create_document():
    async def _create(
        session: AsyncSession,
        user_id: int,
        filename: str,
        description: str,
        mime_type: MimeType,
        file_size: int,
        temp_filename: str,
    ):
        from src.models.documents import Document

        document = Document(
            user_id=user_id,
            filename=filename,
            description=description,
            mime_type=mime_type,
            file_size=file_size,
            temp_filename=temp_filename,
        )

        session.add(document)

        await session.flush()
        await session.refresh(document)

        return {
            "id": document.id,
            "user_id": document.user_id,
            "filename": document.filename,
            "description": document.description,
            "mime_type": document.mime_type,
            "file_size": document.file_size,
            "document_status": document.document_status,
            "document_text": document.document_text,
            "analysis": document.analysis,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    return _create


def get_test_jwt_manager(
    private_key_path: str = str(FIXTURES_DIR / "test_private.pem"),
    public_key_path: str = str(FIXTURES_DIR / "test_public.pem"),
    algorithm: str = "RS256",
) -> JWTManager:
    return JWTManager(private_key_path=private_key_path, public_key_path=public_key_path, algorithm=algorithm)


@pytest.fixture
def create_token_pair(create_user, test_db_session):
    async def _create(
        login: str,
        email: str,
        password_hash: str,
        expired: bool = False,
        is_admin: bool = False,
    ):
        from datetime import datetime, timedelta

        import jwt

        jwt_mgr = get_test_jwt_manager()

        user_data = await create_user(test_db_session, login, email, password_hash)

        now = datetime.now(UTC)
        payload = {
            "sub": user_data["id"],
            "login": user_data["login"],
            "is_admin": is_admin,
        }

        if expired:
            refresh_payload = {**payload, "type": "refresh", "exp": now - timedelta(hours=1)}
            refresh_token = jwt.encode(refresh_payload, jwt_mgr.private_key, algorithm=jwt_mgr.algorithm)
            access_payload = {**payload, "type": "access", "exp": now - timedelta(hours=1)}
            access_token = jwt.encode(access_payload, jwt_mgr.private_key, algorithm=jwt_mgr.algorithm)
        else:
            tokens = jwt_mgr.get_tokens(payload)
            access_token = tokens["access_token"]
            refresh_token = tokens["refresh_token"]

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user_id": user_data["id"],
            "login": user_data["login"],
        }

    return _create


@pytest.fixture
def test_password():
    plain = "SecureTestPass123!"
    return plain, get_password_hash(plain)
