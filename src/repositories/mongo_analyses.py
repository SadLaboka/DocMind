from src.core.enums import AnalysisStatus, LLMProvider
from src.models.mongo_analysis import DocumentAnalysis


class MongoAnalysisRepository:

    async def create_analysis(
        self,
        document_id: int,
        request_id: str,
        provider: LLMProvider,
        **kwargs,
    ) -> DocumentAnalysis:

        analysis = DocumentAnalysis(document_id=document_id, request_id=request_id, provider=provider, **kwargs)

        await analysis.insert()

        return analysis

    async def get_analysis_by_id(self, analysis_id: int) -> DocumentAnalysis | None:
        return await DocumentAnalysis.find_one(id=analysis_id)

    async def get_analysis_by_document_and_request(self, document_id: int, request_id: str) -> DocumentAnalysis | None:
        return await DocumentAnalysis.find_one(document_id=document_id, request_id=request_id)

    async def get_successful_analyses(self, document_id: int) -> list[DocumentAnalysis]:
        return await DocumentAnalysis.find_many(document_id=document_id, status=AnalysisStatus.success).to_list()
