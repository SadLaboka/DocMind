from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.security import HTTPBearer
from starlette import status

from src.DependencyInjection.auth import get_current_user
from src.DependencyInjection.documents import get_document_service, get_upload_service
from src.schemas.documents import DocumentListResponse, DocumentResponse
from src.schemas.users import User
from src.services.documents import DocumentService
from src.services.file_processor import UploadService

router = APIRouter(prefix="/documents", tags=["documents"])
http_bearer = HTTPBearer(auto_error=False)


@router.get(
    path="/",
    summary="Get all documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentListResponse,
)
async def get_all_documents(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    response = await document_service.get_document_list(current_user, page, limit)

    return response


@router.get(
    path="/{document_id}",
    summary="Get document by document_id",
    status_code=status.HTTP_200_OK,
    response_model=DocumentResponse,
)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    return await document_service.get_document_by_id(document_id, current_user)


@router.post(
    path="/",
    summary="Load document",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def upload_document(
    description: Annotated[str, Form(max_length=300)],
    request: Request,
    file: UploadFile = File(...),
    service: UploadService = Depends(get_upload_service),
    current_user: User = Depends(get_current_user),
) -> DocumentResponse:

    return await service.process_upload(file, current_user.id, description, request.state.request_id)
