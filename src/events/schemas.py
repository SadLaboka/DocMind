from pydantic import BaseModel


class AnalysisRequestedEvent(BaseModel):
    analysis_id: str
    document_id: int
    user_id: int
    request_id: str
