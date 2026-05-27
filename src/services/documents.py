
from src.core.exceptions import ResourceNotFoundError
from src.repositories.documents import DocumentRepository
from src.schemas.documents import DocumentListResponse, DocumentResponse
from src.schemas.users import User
from src.services.base import BaseService


class DocumentService(BaseService[DocumentRepository]):
    """Service for documents"""
    async def get_document_by_id(self, document_id: int, user: User) -> DocumentResponse:
        """Gets a document from the database by id, checks the document's ownership and returns it"""
        if user.is_admin:
            document = await self.repository.get_document_by_id(document_id)
        else:
            document = await self.repository.get_document_by_id_and_user(document_id, user.id)

        if not document:
            raise ResourceNotFoundError(
                error_code="document_not_found",
                message="Document not found",
                log_context = {
                    "user_id": user.id,
                    "is_admin": user.is_admin,
                    "document_id": document_id,
                }
            )
        return DocumentResponse.model_validate(document)

    async def get_document_list(
            self, user: User, page: int, limit: int) -> DocumentListResponse:
        """Gets a list of documents from the database by user_id, constructs pagination and returns it"""
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
