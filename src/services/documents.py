from fastapi import HTTPException

from src.services.base import BaseService
from src.repositories.documents import DocumentRepository
from src.schemas.documents import DocumentResponse, DocumentListResponse
from src.schemas.users import User


class DocumentService(BaseService[DocumentRepository]):
    async def get_document_by_id(self, document_id: int, user: User) -> DocumentResponse:
        if user.is_admin:
            document = await self.repository.get_document_by_id(document_id)
        else:
            document = await self.repository.get_document_by_id_and_user(document_id, user.id)

        if not document:
            raise HTTPException(status_code=404, detail="Document not found")
        return DocumentResponse.model_validate(document)

    async def get_document_list(
            self, user: User, page: int, limit: int) -> DocumentListResponse:
        offset = (page - 1) * limit

        documents = await self.repository.get_documents_list(
            user_id=user.id,
            offset=offset,
            limit=limit
        )

        documents_count = await self.repository.get_documents_count(user_id=user.id)

        has_next = documents_count > limit * page


        return DocumentListResponse.model_validate({
            "items": documents,
            "has_next": has_next,
            "page": page,
            "limit": limit,
            "total": documents_count
        })
