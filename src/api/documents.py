from fastapi import APIRouter, Depends, File, UploadFile, Query, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette import status
from typing import Annotated

from src.DependencyInjection.documents import get_upload_service, get_document_service
from src.DependencyInjection.auth import get_jwt_manager
from src.schemas.documents import DocumentListResponse, DocumentResponse
from src.schemas.users import User
from src.services.file_processor import UploadService
from src.services.documents import DocumentService
from src.core.jwt import JWTManager

router = APIRouter(prefix="/documents", tags=["documents"])
http_bearer = HTTPBearer(auto_error=False)


@router.get(
    path="/",
    summary="Get all documents",
    status_code=status.HTTP_200_OK,
    response_model=DocumentListResponse,
)
async def get_all_documents(
        page:  Annotated[int, Query(ge=1)] = 1,
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
        credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
        jwt_manager: JWTManager = Depends(get_jwt_manager),
        document_service: DocumentService = Depends(get_document_service)
) -> DocumentListResponse:
    token = credentials.credentials
    token_payload = jwt_manager.get_payload_from_access_token(token)
    user = User(
        id=int(token_payload["sub"]),
        login=token_payload["login"],
        is_admin=token_payload["is_admin"]
    )
    response = await document_service.get_document_list(
        user,
        page,
        limit
    )

    return response


@router.get(
    path="/{document_id}",
    summary="Get document by document_id",
    status_code=status.HTTP_200_OK,
    response_model=DocumentResponse,
)
async def get_document(
        document_id: int,
        credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
        jwt_manager: JWTManager = Depends(get_jwt_manager),
        document_service: DocumentService = Depends(get_document_service)
) -> DocumentResponse:
    token = credentials.credentials
    token_payload = jwt_manager.get_payload_from_access_token(token)
    user = User(
        id=int(token_payload["sub"]),
        login=token_payload["login"],
        is_admin=token_payload["is_admin"]
    )
    response = await document_service.get_document_by_id(document_id, user)

    return response

@router.post(
    path="/",
    summary="Load document",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentResponse,
)
async def upload_document(
        description: Annotated[str, Form(max_length=300)],
        file: UploadFile = File(...),
        service: UploadService = Depends(get_upload_service),
        credentials: HTTPAuthorizationCredentials = Depends(http_bearer),
        jwt_manager: JWTManager = Depends(get_jwt_manager)
) -> DocumentResponse:
    token = credentials.credentials
    token_payload = jwt_manager.get_payload_from_access_token(token)
    user = User(
        id=int(token_payload["sub"]),
        login=token_payload["login"],
        is_admin=token_payload["is_admin"]
    )

    response = await service.process_upload(file, user.id, description)
    return response
