from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.repositories.mongo_documents import MongoDocumentRepository
from src.core.database import get_session
from src.repositories.documents import DocumentRepository
from src.services.documents import DocumentService
from src.services.file_processor import UploadService


def get_document_repository(session: AsyncSession = Depends(get_session)) -> DocumentRepository:
    return DocumentRepository(session)


def get_mongo_document_repository() -> MongoDocumentRepository:
    return MongoDocumentRepository()


def get_upload_service(
        repository: DocumentRepository = Depends(get_document_repository),
        mongo_repository: MongoDocumentRepository = Depends(get_mongo_document_repository)
) -> UploadService:
    return UploadService(repository, mongo_repository)


def get_document_service(
        repository: DocumentRepository = Depends(get_document_repository),
        mongo_repository: MongoDocumentRepository = Depends(get_mongo_document_repository)
) -> DocumentService:
    return DocumentService(repository, mongo_repository)
