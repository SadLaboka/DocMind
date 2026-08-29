import datetime
from beanie import BeanieObjectId

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

    async def get_analysis_by_id(self, analysis_id: BeanieObjectId) -> DocumentAnalysis | None:
        return await DocumentAnalysis.get(analysis_id)

    async def get_analysis_by_document_and_request(self, document_id: int, request_id: str) -> DocumentAnalysis | None:
        return await DocumentAnalysis.find_one(DocumentAnalysis.document_id == document_id, DocumentAnalysis.request_id == request_id)

    async def get_successful_analyses(self, document_id: int) -> list[DocumentAnalysis]:
        return await (DocumentAnalysis.find_many(
            DocumentAnalysis.document_id == document_id,
            DocumentAnalysis.status == AnalysisStatus.success)
                      .sort("-created_at")
                      .to_list())

    async def update_analysis_fields(
            self,
            document_id: int,
            request_id: str,
            **kwargs,
    ) -> DocumentAnalysis | None:
        analysis = await self.get_analysis_by_document_and_request(document_id, request_id)
        if analysis:
            for key, value in kwargs.items():
                setattr(analysis, key, value)

            analysis.updated_at = datetime.datetime.now(datetime.UTC)

            await analysis.save()
            return analysis
        return None
