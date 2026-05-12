from fastapi import APIRouter, Query
from starlette import status

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get(
    path="/",
    summary="Get all documents",
    status_code=status.HTTP_200_OK,
)
async def get_all_documents(
    user_id: int | None = Query(None, description="Filter by user id"),
):
    return {"documents": "documents by user_id"} if user_id else {"documents": "list of documents"}


@router.get(
    path="/{document_id}",
    summary="Get document by document_id",
    status_code=status.HTTP_200_OK,
)
async def get_document(document_id: int):
    return {"document_id": document_id}


@router.post(
    path="/",
    summary="Load document",
    status_code=status.HTTP_201_CREATED,
)
async def upload_document():
    return {"status": "loaded", "id": "document_id"}
