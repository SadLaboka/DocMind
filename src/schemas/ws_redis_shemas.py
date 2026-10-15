from src.schemas.ws_messages import DocumentStatusChanged, AnalysisStatusChanged

from typing import Literal, Union

from pydantic import BaseModel, Field


class RedisStatusNotification(BaseModel):
    type: Literal["notification"]
    user_id: int
    event: Union[DocumentStatusChanged, AnalysisStatusChanged] = Field(discriminator="type")


class RedisUserDeactivated(BaseModel):
    type: Literal["auth.user_deactivated"]
    user_id: int
