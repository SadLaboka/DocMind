from fastapi import APIRouter, Query
from starlette import status

from src.schemas.documents import DocumentListResponse, DocumentResponse, DocumentUpload

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    path="/",
    summary="Get all documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentListResponse,
)
async def get_all_documents(
    user_id: int | None = Query(None, description="Filter by user id"),
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
    response_model=DocumentUpload,
)
async def upload_document() -> DocumentUpload:
    return {"status": "loaded", "id": "document_id"}
