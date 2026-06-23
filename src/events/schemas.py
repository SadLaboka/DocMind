from pydantic import BaseModel


class DocumentTextExtractedEvent(BaseModel):
    document_id: int
    mime_type: str
    user_id: int
    request_id: str
    provider: str
