from pathlib import Path

import structlog

from src.models.mongo_documents import MongoDocument
from src.core.config import settings
from src.core.enums import DocumentStatus
from src.core.exceptions import ResourceNotFoundError
from src.models.documents import Document
from src.repositories.documents import DocumentRepository
from src.schemas.documents import DocumentListResponse, DocumentResponse
from src.schemas.users import User
from src.services.base import BaseService

logger = structlog.get_logger(__name__)


class DocumentService(BaseService[DocumentRepository]):
    """Service for documents"""

    async def get_document_by_id(self, document_id: int, user: User) -> DocumentResponse:
        """Gets document by document_id"""

        document = await self._get_document(user, document_id)

        logger.info(
            "document_retrieved",
            document_id=document.id,
            user_id=user.id,
            filename=document.filename,
        )

        response = DocumentResponse.model_validate(document)

        try:
            doc_content = await self._get_document_content(document.id)
        except Exception as err:
            logger.error(
                "mongo_connection_error",
                document_id=document.id,
                error=str(err),
            )
            doc_content = None

        if doc_content:
            logger.info(
                "document_content_retrieved",
                document_id=document.id,
                user_id=user.id,
            )

            response.document_text = doc_content.raw_text
            response.analysis = doc_content.analysis
            response.analysis_version = doc_content.analysis_version

        else:
            logger.info(
                "document_content_not_found",
                document_id=document.id,
                user_id=user.id,
            )


        return response

    async def get_document_list(self, user: User, page: int, limit: int) -> DocumentListResponse:
        """Gets a list of documents from the database by user_id, constructs pagination and returns it"""
        offset = (page - 1) * limit

        documents = await self.repository.get_documents_list(user_id=user.id, offset=offset, limit=limit)

        documents_count = await self.repository.get_documents_count(user_id=user.id)

        has_next = documents_count > limit * page

        logger.info(
            "document_list_retrieved",
            user_id=user.id,
            page=page,
            limit=limit,
            total_found=documents_count,
            returned_count=len(documents),
        )

        return DocumentListResponse.model_validate(
            {"items": documents, "has_next": has_next, "page": page, "limit": limit, "total": documents_count}
        )

    async def cancel_document_processing(self, user: User, document_id: int) -> DocumentResponse:
        """Changes document status to canceled and removes it from temp directory if it needs"""

        logger.info(
            "document_canceling_initiation",
            user_id=user.id,
            document_id=document_id,
        )

        document = await self._get_document(user, document_id)

        if document.document_status != DocumentStatus.cancelled:
            temp_filename_to_delete = document.temp_filename

            updated_document = await self.repository.update_document_fields(
                document_id=document_id, document_status=DocumentStatus.cancelled, temp_filename=None
            )
            if temp_filename_to_delete:
                path = Path(settings.base_dir).parent / "temp" / temp_filename_to_delete

                if path.exists():
                    path.unlink(missing_ok=True)

            if not updated_document:
                raise ResourceNotFoundError(
                    error_code="document_not_found",
                    message="Document not found",
                    log_context={
                        "event_name": "document_not_found",
                        "reason": "document was removed from database before cancelling",
                        "user_id": user.id,
                        "document_id": document_id,
                    },
                )

        else:
            logger.info("document_already_cancelled", document_id=document_id, user_id=user.id)
            return DocumentResponse.model_validate(document)

        logger.info(
            "document_cancelled",
            document_id=document_id,
            user_id=user.id,
        )

        return DocumentResponse.model_validate(updated_document)

    async def _get_document(self, user: User, document_id: int) -> Document:
        """Gets a document from the database by id, checks the document's ownership and returns it"""
        if user.is_admin:
            document = await self.repository.get_document_by_id(document_id)
        else:
            document = await self.repository.get_document_by_id_and_user(document_id, user.id)

        if not document:
            raise ResourceNotFoundError(
                error_code="document_not_found",
                message="Document not found",
                log_context={
                    "event_name": "document_not_found",
                    "user_id": user.id,
                    "is_admin": user.is_admin,
                    "document_id": document_id,
                },
            )

        return document

    async def _get_document_content(self, document_id: int) -> MongoDocument | None:
        """Gets a document content from mongo database"""
        return await self.mongo_repository.get_content(document_id)
