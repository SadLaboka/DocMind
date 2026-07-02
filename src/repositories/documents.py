from sqlalchemy import and_, func, select

from src.core.enums import DocumentStatus, LLMProvider
from src.models.documents import Document
from src.repositories.base import BaseRepository
from src.schemas.documents import DocumentData


class DocumentRepository(BaseRepository):
    async def create_document(self, data: DocumentData) -> Document:
        document = Document(**data.model_dump())

        self.session.add(document)
        await self.session.flush()

        return document

    async def get_document_by_id(self, document_id: int) -> Document | None:
        result = await self.session.execute(select(Document).where(Document.id == document_id))
        document = result.scalar_one_or_none()
        return document

    async def get_document_by_id_and_user(self, document_id: int, user_id: int) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )
        document = result.scalar_one_or_none()
        return document

    async def get_documents_list(self, user_id: int, offset: int, limit: int) -> list[Document]:
        stmt = (
            select(Document).where(Document.user_id == user_id).offset(offset).limit(limit).order_by(Document.id.desc())
        )
        result = await self.session.execute(stmt)
        documents = result.scalars().all()

        return list(documents)

    async def get_documents_count(self, user_id: int) -> int:
        stmt = select(func.count(Document.id)).select_from(Document).where(Document.user_id == user_id)
        return await self.session.scalar(stmt) or 0

    async def update_document_fields(self, document_id: int, **data) -> Document | None:
        document = await self.get_document_by_id(document_id)
        if document is None:
            return None

        for key, value in data.items():
            setattr(document, key, value)

        await self.session.commit()
        await self.session.refresh(document)
        return document

    async def get_document_by_hash_and_active_status_and_provider(
        self, file_hash: str, provider: LLMProvider
    ) -> Document | None:
        stmt = select(Document).where(
            and_(
                Document.file_hash == file_hash,
                Document.document_status.in_([DocumentStatus.success, DocumentStatus.extracted]),
                Document.provider == provider,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
