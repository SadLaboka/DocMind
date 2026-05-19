from src.repositories.base import BaseRepository
from src.schemas.documents import DocumentData
from src.models.documents import Document


class DocumentRepository(BaseRepository):
    async def create_document(self, data: DocumentData) -> Document:
        document = Document(**data.model_dump())

        self.session.add(document)
        await self.session.flush()

        return document
