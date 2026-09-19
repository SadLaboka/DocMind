import datetime
from typing import Any

from beanie import BeanieObjectId, SortDirection
from beanie.operators import In

from src.core.enums import AnalysisStatus, LLMProvider
from src.models.mongo_analysis import DocumentAnalysis


class MongoAnalysisRepository:

    async def create_analysis(
        self,
        document_id: int,
        request_id: str,
        provider: LLMProvider,
        prompt_version: str | None = None,
        retry_of_analysis_id: BeanieObjectId | None = None,
    ) -> DocumentAnalysis:

        analysis = DocumentAnalysis(
            document_id=document_id, request_id=request_id, provider=provider, prompt_version=prompt_version
        )

        if retry_of_analysis_id is not None:
            analysis.retry_of_analysis_id = retry_of_analysis_id

        await analysis.insert()

        return analysis

    async def get_analysis_by_id(self, analysis_id: BeanieObjectId) -> DocumentAnalysis | None:
        return await DocumentAnalysis.get(analysis_id)

    async def get_analysis_by_document_and_request(self, document_id: int, request_id: str) -> DocumentAnalysis | None:
        return await DocumentAnalysis.find_one(
            DocumentAnalysis.document_id == document_id, DocumentAnalysis.request_id == request_id
        )

    async def get_successful_analyses(self, document_id: int) -> list[DocumentAnalysis]:
        return await (
            DocumentAnalysis.find_many(
                DocumentAnalysis.document_id == document_id, DocumentAnalysis.status == AnalysisStatus.success
            )
            .sort("-created_at")
            .to_list()
        )

    async def get_analyses_by_document_id(
            self,
            document_id: int,
            limit: int | None = None,
            skip: int = 0,
            statuses: list[AnalysisStatus] | None = None,
            providers: list[LLMProvider] | None = None,
    ) -> list[DocumentAnalysis]:

        filters: list[Any] = [DocumentAnalysis.document_id == document_id]

        if statuses:
            filters.append(In(DocumentAnalysis.status, statuses))

        if providers:
            filters.append(In(DocumentAnalysis.provider, providers))

        return await (
            DocumentAnalysis.find_many(
                *filters,
                sort=[("created_at", SortDirection.DESCENDING), ("id", SortDirection.DESCENDING)],
                limit=limit,
                skip=skip,
            )
            .to_list()
        )

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
