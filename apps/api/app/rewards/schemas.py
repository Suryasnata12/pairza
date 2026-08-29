import uuid
from datetime import datetime

from pydantic import BaseModel


class BadgeOut(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str
    icon: str
    earned: bool
    earned_at: datetime | None = None

    model_config = {"from_attributes": True}


class RewardOut(BaseModel):
    id: uuid.UUID
    type: str
    amount: int
    reason: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    mystery_title: str
    partner_country_code: str
    solved: bool
    solve_seconds: float | None
    anonymous_message: str | None
    day_number: int
    created_at: datetime

    model_config = {"from_attributes": True}


class SolveResult(BaseModel):
    xp_awarded: int
    new_badge_codes: list[str]
