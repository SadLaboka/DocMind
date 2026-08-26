import datetime

from beanie.operators import In, NotIn, Set

from src.core.enums import LLMProvider
from src.models.mongo_analysis import DocumentAnalysis


class MongoAnalysisRepository:

    async def create_analysis(
            self,
            document_id: int,
            request_id: str,
            provider: LLMProvider,
            **kwargs,
    ) -> DocumentAnalysis:

        analysis = DocumentAnalysis(
            document_id=document_id,
            request_id=request_id,
            provider=provider,
            **kwargs
        )

        await analysis.insert()

        return analysis
