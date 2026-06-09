from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from src.core.config import settings

engine = create_async_engine(settings.db.url, future=True, echo=settings.logs.dev)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

celery_engine = create_async_engine(settings.db.url, future=True, echo=settings.logs.dev, poolclass=NullPool)
celery_session_factory = async_sessionmaker(celery_engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession]:

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
