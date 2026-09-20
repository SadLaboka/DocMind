from fastapi import Depends

from src.repositories.mongo_analyses import MongoAnalysisRepository
from src.services.analysis import AnalysisService


def get_analysis_repository() -> MongoAnalysisRepository:
    return MongoAnalysisRepository()


def get_analysis_service(
    analysis_repository: MongoAnalysisRepository = Depends(get_analysis_repository),
) -> AnalysisService:
    return AnalysisService(analysis_repository)
