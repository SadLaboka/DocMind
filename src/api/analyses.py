from fastapi import APIRouter, Depends, Query
from starlette import status

from src.core.enums import AnalysisStatus, LLMProvider
from src.DependencyInjection.analyses import get_analysis_service
from src.DependencyInjection.auth import get_current_user
from src.DependencyInjection.documents import get_document_service
from src.schemas.analyses import AnalysesListResponse, AnalysisResponse
from src.schemas.users import User
from src.services.analysis import AnalysisService
from src.services.documents import DocumentService

router = APIRouter(prefix="/documents/{document_id}/analyses", tags=["analysis"])


@router.get(
    "/",
    summary="Get all analyses by document",
    status_code=status.HTTP_200_OK,
    response_model=AnalysesListResponse,
)
async def get_all_analyses(
    document_id: int,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=20, description="Page size"),
    statuses: list[AnalysisStatus] = Query(default=[], description="Statuses filter"),
    providers: list[LLMProvider] = Query(default=[], description="Providers filter"),
    current_user: User = Depends(get_current_user),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    document_service: DocumentService = Depends(get_document_service),
) -> AnalysesListResponse:
    await document_service.get_document(current_user, document_id)

    return await analysis_service.get_analyses_list(
        document_id, limit=limit, page=page, user_id=current_user.id, analyses_statuses=statuses, providers=providers
    )


@router.get(
    "/{analysis_id}",
    summary="Get analysis by analysis id",
    status_code=status.HTTP_200_OK,
    response_model=AnalysisResponse,
)
async def get_analysis(
        analysis_id: str,
        document_id: int,
        current_user: User = Depends(get_current_user),
        analysis_service: AnalysisService = Depends(get_analysis_service),
        document_service: DocumentService = Depends(get_document_service),
) -> AnalysisResponse:
    await document_service.get_document(current_user, document_id)

    return await analysis_service.get_analysis(analysis_id=analysis_id, document_id=document_id, user_id=current_user.id)
