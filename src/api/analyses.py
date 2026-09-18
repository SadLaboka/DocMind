from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPBearer
from starlette import status

from src.core.enums import AnalysisStatus, LLMProvider
from src.DependencyInjection.analyses import get_analysis_service
from src.DependencyInjection.auth import get_auth_service
from src.DependencyInjection.documents import get_document_service
from src.schemas.analyses import AnalysesListReponse
from src.schemas.users import User
from src.services.analysis import AnalysisService
from src.services.documents import DocumentService

router = APIRouter(prefix="/analysis{document_id}", tags=["analysis"])
http_bearer = HTTPBearer(auto_error=False)


@router.get(
    "/",
    summary="Get all analyses by document",
    status_code=status.HTTP_200_OK,
    response_model=AnalysesListReponse,
)
async def get_all_analyses(
    document_id: int,
    page: int = Query(0, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=20, description="Page size"),
    statuses: list[AnalysisStatus] = Query(default=[], description="Statuses filter"),
    providers: list[LLMProvider] = Query(default=[], description="Providers filter"),
    current_user: User = Depends(get_auth_service),
    analysis_service: AnalysisService = Depends(get_analysis_service),
    document_service: DocumentService = Depends(get_document_service),
) -> AnalysesListReponse:
    await document_service.get_document_by_id(document_id, current_user)

    return await analysis_service.get_analyses_list(
        document_id,
        limit=limit,
        page=page,
        analyses_statuses=statuses,
        providers=providers
    )
