from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_session
from src.repositories.documents import DocumentRepository
from src.services.file_processor import UploadService


def get_document_repository(session: AsyncSession = Depends(get_session)) -> DocumentRepository:
    return DocumentRepository(session)


def get_upload_service(repository: DocumentRepository = Depends(get_document_repository)) -> UploadService:
    return UploadService(repository)
