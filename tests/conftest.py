from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from main import app
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from src.core.config import settings
from src.core.database import get_session
from src.core.enums import DocumentStatus, LLMProvider, MimeType
from src.core.jwt import JWTManager
from src.core.security import get_password_hash
from src.core.token_blacklist import TokenBlackList
from src.core.user_active_cache import UserActiveStatusCache
from src.DependencyInjection.auth import (
    get_jwt_manager,
    get_token_blacklist,
    get_user_active_cache,
)
from src.DependencyInjection.documents import get_mongo_document_repository
from src.DependencyInjection.prompts import get_mongo_prompt_repository
from src.repositories.documents import DocumentRepository
from src.repositories.mongo_documents import MongoDocumentRepository
from src.repositories.mongo_prompts import MongoPromptsRepository
from src.storage.s3_storage import S3Storage

TEST_DB_URL = settings.db.url
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# DB Fixtures


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


# Worker mocks


WORKER_SESSION_FACTORY_TARGETS = (
    "src.worker.base_task.celery_session_factory",
    "src.worker.extraction_tasks.celery_session_factory",
    "src.worker.antivirus_tasks.celery_session_factory",
    "src.worker.s3_upload_task.celery_session_factory",
)

WORKER_REPOSITORY_TARGETS = (
    "src.worker.base_task.DocumentRepository",
    "src.worker.extraction_tasks.DocumentRepository",
    "src.worker.antivirus_tasks.DocumentRepository",
    "src.worker.s3_upload_task.DocumentRepository",
)


@pytest.fixture
def mock_celery_session():

    mock_session = AsyncMock(spec=AsyncSession)

    context_manager = MagicMock()
    context_manager.__aenter__ = AsyncMock(return_value=mock_session)
    context_manager.__aexit__ = AsyncMock(return_value=None)

    with ExitStack() as stack:
        for target in WORKER_SESSION_FACTORY_TARGETS:
            mock_factory = stack.enter_context(patch(target))
            mock_factory.return_value = context_manager

        yield mock_session


@pytest.fixture
def mock_worker_repo():

    mock_repo = AsyncMock(spec=DocumentRepository)
    mock_repo.get_document_by_id.return_value = MagicMock(
        document_status=DocumentStatus.created,
    )

    with ExitStack() as stack:
        for target in WORKER_REPOSITORY_TARGETS:
            mock_repository_class = stack.enter_context(patch(target))
            mock_repository_class.return_value = mock_repo

        yield mock_repo


@pytest.fixture
def mock_path_operations():

    with (
        patch("pathlib.Path.exists", return_value=True) as mock_exists,
        patch("pathlib.Path.unlink") as mock_unlink,
    ):
        yield mock_exists, mock_unlink


# Storage mocks


@pytest.fixture
def s3_storage():
    return S3Storage(
        endpoint_url="http://localhost:9000",
        access_key="test_access_key",
        secret_key="test_secret_key",
        region="us-east-1",
        bucket="test-bucket",
        presigned_url_ttl=3600,
    )


@pytest.fixture
def mock_s3_client():

    client = MagicMock()
    client.upload_file = AsyncMock()
    client.delete_object = AsyncMock()
    client.head_object = AsyncMock()
    client.generate_presigned_url = AsyncMock(return_value="https://signed-url")
    return client


@pytest.fixture
def temp_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    return file_path


# Mongo mocks


class MockMongoContent(BaseModel):
    document_id: int
    raw_text: str | None = None
    analysis: dict | None = None
    analysis_version: str | None = None


@pytest.fixture
def mongo_content_factory():
    def content(document_id: int = 1, raw_text: str | None = None):
        return MockMongoContent(
            document_id=document_id,
            raw_text=raw_text,
            analysis=None,
            analysis_version=None,
        )

    return content


@pytest.fixture
def mock_mongo_content(request, mongo_content_factory):
    params = getattr(request, "param", {})
    return mongo_content_factory(**params)


@pytest.fixture
def mock_mongo_repo(mock_mongo_content):
    mock_repo = AsyncMock(spec=MongoDocumentRepository)

    mock_repo.get_content.return_value = mock_mongo_content
    mock_repo.create_content.return_value = mock_mongo_content
    mock_repo.get_content_for_deduplicate.return_value = mock_mongo_content
    mock_repo.upsert_raw_text.return_value = mock_mongo_content
    return mock_repo

# Redis mocks


@pytest.fixture
def mock_token_blacklist():
    mock = AsyncMock(spec=TokenBlackList)
    mock.is_blacklisted = AsyncMock(return_value=False)
    mock.add_to_blacklist = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_user_active_cache():
    mock = AsyncMock(spec=UserActiveStatusCache)
    mock.get_active = AsyncMock(return_value=True)
    mock.set_active = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def mock_mongo_prompt_repository():
    return AsyncMock(spec=MongoPromptsRepository)


# Client


@pytest_asyncio.fixture(scope="function")
async def client(
    test_db_session,
    mock_mongo_repo,
    mock_token_blacklist,
    mock_user_active_cache,
    mock_mongo_prompt_repository,
):
    async def override_get_session():
        yield test_db_session

    def override_get_mongo_repo():
        return mock_mongo_repo

    app.dependency_overrides[get_mongo_document_repository] = override_get_mongo_repo
    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_jwt_manager] = get_test_jwt_manager
    app.dependency_overrides[get_token_blacklist] = lambda: mock_token_blacklist
    app.dependency_overrides[get_user_active_cache] = lambda: mock_user_active_cache
    app.dependency_overrides[get_mongo_prompt_repository] = lambda: mock_mongo_prompt_repository

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# Factories


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
        _id: int | None = None,
        temp_filename: str | None = None,
        document_status: DocumentStatus = DocumentStatus.created,
        file_hash: str | None = None,
        provider: LLMProvider | None = None,
        file_key: str | None = None,
    ):
        from src.models.documents import Document

        if not provider:
            provider = LLMProvider(settings.llm.default_provider)

        document = Document(
            user_id=user_id,
            filename=filename,
            description=description,
            mime_type=mime_type,
            file_size=file_size,
            temp_filename=temp_filename,
            provider=provider,
            document_status=document_status,
            file_hash=file_hash,
            file_key=file_key,
        )
        if _id:
            document.id = _id
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
            "temp_filename": document.temp_filename,
            "document_status": document.document_status,
            "file_hash": document.file_hash,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
            "provider": document.provider,
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
        from datetime import timedelta

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
def create_admin_token_pair(create_token_pair, test_password):
    async def _create(
        login: str = "admin",
        email: str = "admin@test.com",
        password_hash: str | None = None,
        expired: bool = False,
    ):
        if password_hash is None:
            _, password_hash = test_password

        return await create_token_pair(
            login=login,
            email=email,
            password_hash=password_hash,
            expired=expired,
            is_admin=True,
        )

    return _create


@pytest.fixture
def test_password():
    plain = "SecureTestPass123!"
    return plain, get_password_hash(plain)
