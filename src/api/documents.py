from fastapi import APIRouter, Depends, File, UploadFile
from starlette import status

from src.DependencyInjection.documents import get_upload_service
from src.schemas.documents import DocumentListResponse, DocumentResponse
from src.services.file_processor import UploadService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    path="/",
    summary="Get all documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentListResponse,
)
async def get_all_documents(
    user_id: int | None,
) -> DocumentListResponse:
    return {"documents": "documents by user_id"} if user_id else {"documents": "list of documents"}


@router.get(
    path="/{document_id}",
    summary="Get document by document_id",
    status_code=status.HTTP_200_OK,
    response_model=DocumentResponse,
)
async def get_document(document_id: int) -> DocumentResponse:
    return {"document_id": document_id}


@router.post(
    path="/",
    summary="Load document",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def upload_document(
        file: UploadFile = File(...),
        service: UploadService = Depends(get_upload_service),
) -> DocumentResponse:
    user_id = 1
    description = "mock"
    response = await service.process_upload(file, user_id, description)
    return response
