from src.core.enums import DocumentStatus, AnalysisStatus

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


class Auth(BaseModel):
    type: Literal["auth"]
    access_token: str = Field(description="access token", min_length=1)

    model_config = ConfigDict(extra="forbid")


class Ready(BaseModel):
    type: Literal["ready"] = "ready"

    model_config = ConfigDict(extra="forbid")


class SyncRequired(BaseModel):
    type: Literal["sync_required"] = "sync_required"

    model_config = ConfigDict(extra="forbid")


class DocumentStatusChanged(BaseModel):
    type: Literal["document.status_changed"] = "document.status_changed"
    document_id: int
    status: DocumentStatus
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")


class AnalysisStatusChanged(BaseModel):
    type: Literal["analysis.status_changed"] = "analysis.status_changed"
    document_id: int
    analysis_id: str
    status: AnalysisStatus
    updated_at: datetime

    model_config = ConfigDict(extra="forbid")
