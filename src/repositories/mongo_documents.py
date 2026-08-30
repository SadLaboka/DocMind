import datetime

from beanie.operators import In, NotIn, Set

from src.models.mongo_documents import MongoDocument


class MongoDocumentRepository:

    async def create_content(
        self,
        document_id: int,
        raw_text: str | None = None,
    ) -> MongoDocument:
        document_content = MongoDocument(document_id=document_id, raw_text=raw_text)

        await document_content.insert()

        return document_content

    async def upsert_raw_text(self, document_id: int, raw_text: str) -> None:
        await MongoDocument.find_one(MongoDocument.document_id == document_id).upsert(
            Set(
                {
                    MongoDocument.raw_text: raw_text,
                    MongoDocument.updated_at: datetime.datetime.now(datetime.UTC),
                }
            ),
            on_insert=MongoDocument(document_id=document_id, raw_text=raw_text),
        )

    async def get_content(self, document_id: int) -> MongoDocument | None:
        return await MongoDocument.find_one(MongoDocument.document_id == document_id)

    async def get_content_for_deduplicate(self, candidates_ids: list[int]) -> MongoDocument | None:
        content = await MongoDocument.find_one(
            In(MongoDocument.document_id, candidates_ids),
            NotIn(MongoDocument.raw_text, [None, ""]),
        )

        return content

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
