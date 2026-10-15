from src.schemas.ws_messages import DocumentStatusChanged, AnalysisStatusChanged

from typing import Literal, Union

from pydantic import BaseModel


class RedisStatusNotification(BaseModel):
    type: Literal["notification"] = "notification"
    user_id: int
    event: Union[DocumentStatusChanged, AnalysisStatusChanged]


class RedisUserDeactivated(BaseModel):
    type: Literal["auth.user_deactivated"] = "auth.user_deactivated"
    user_id: int
