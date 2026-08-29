import uuid
from datetime import datetime

from pydantic import BaseModel, Field

REPORT_REASONS = [
    "harassment", "hate_speech", "spam", "inappropriate_content",
    "impersonation", "underage", "self_harm_concern", "other",
]


class ReportCreate(BaseModel):
    reported_user_id: uuid.UUID
    session_id: uuid.UUID | None = None
    reason: str = Field(pattern="^(" + "|".join(REPORT_REASONS) + ")$")
    details: str | None = Field(default=None, max_length=2000)


class ReportOut(BaseModel):
    id: uuid.UUID
    reported_user_id: uuid.UUID
    reason: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class BlockCreate(BaseModel):
    blocked_id: uuid.UUID


class BlockOut(BaseModel):
    id: uuid.UUID
    blocked_id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
