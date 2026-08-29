import uuid
from datetime import datetime

from pydantic import BaseModel


class MatchmakingStatusResponse(BaseModel):
    status: str  # "idle" | "waiting" | "matched"
    session_id: uuid.UUID | None = None
    expires_at: datetime | None = None
    partner_country_code: str | None = None
