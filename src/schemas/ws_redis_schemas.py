from src.schemas.ws_messages import DocumentStatusChanged, AnalysisStatusChanged

from typing import Literal, Union

from pydantic import BaseModel, Field, ConfigDict


class RedisStatusNotification(BaseModel):
    type: Literal["notification"]
    user_id: int = Field(gt=0)
    event: Union[DocumentStatusChanged, AnalysisStatusChanged] = Field(discriminator="type")

    model_config = ConfigDict(extra="forbid")


class RedisUserDeactivated(BaseModel):
    type: Literal["auth.user_deactivated"]
    user_id: int = Field(gt=0)

    model_config = ConfigDict(extra="forbid")
