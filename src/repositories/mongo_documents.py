import datetime
from src.models.mongo_documents import MongoDocument


class MongoDocumentRepository:

    async def create_content(
            self,
            document_id: int,
            raw_text: str | None = None,
            analysis: dict | None = None,
            analysis_version: str | None = None
    ) -> MongoDocument:
        document_content = MongoDocument(
            document_id=document_id,
            raw_text=raw_text,
            analysis=analysis,
            analysis_version=analysis_version
        )

        await document_content.insert()

        return document_content

    async def get_content(self, document_id: int) -> MongoDocument | None:
        return await MongoDocument.find_one(MongoDocument.document_id == document_id)

    async def create_duplicate_content(self, original_doc_id: int, new_doc_id: int) -> MongoDocument | None:
        original_doc = await self.get_content(original_doc_id)
        if original_doc:
            new_doc = MongoDocument(
                document_id=new_doc_id,
                raw_text=original_doc.raw_text,
                analysis=original_doc.analysis,
                analysis_version=original_doc.analysis_version
            )
            await new_doc.insert()
            return new_doc

        return None

    async def update_content(self, document_id: int, **kwargs) -> MongoDocument | None:
        document_content = await self.get_content(document_id)
        if document_content:
            for key, value in kwargs.items():
                setattr(document_content, key, value)

                document_content.updated_at = datetime.datetime.now(datetime.UTC)

            await document_content.save()

            return document_content
        return None

    async def delete_content(self, document_id: int) -> bool:
        content = await self.get_content(document_id)
        if not content:
            return False

        await content.delete()

        return True
