import uuid
from datetime import datetime

from pydantic import BaseModel


class MessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    sender_id: uuid.UUID | None
    type: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageSendIn(BaseModel):
    content: str
