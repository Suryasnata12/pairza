import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.mysteries.schemas import MysteryDetailForSession


class PartnerTeaser(BaseModel):
    """Section 11 — deliberately excludes exact location, IP, email, phone, social accounts."""

    country_code: str
    timezone_region: str
    interests: list[str]
    language: str
    puzzle_experience_level: str


class EvidenceOut(BaseModel):
    id: uuid.UUID
    title: str
    content: str
    source_url: str | None
    submitted_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class EvidenceCreate(BaseModel):
    title: str = Field(max_length=200)
    content: str
    source_url: str | None = None


class SessionDetailResponse(BaseModel):
    id: uuid.UUID
    status: str
    current_stage_number: int
    started_at: datetime
    expires_at: datetime
    seconds_remaining: int
    solved_at: datetime | None
    your_role: str
    mystery: MysteryDetailForSession
    partner: PartnerTeaser | None
    partner_id: uuid.UUID | None  # opaque id needed for block/report — not PII, unlike PartnerTeaser's fields
    evidence: list[EvidenceOut]
    wrong_attempt_count: int = 0


class AnswerSubmitRequest(BaseModel):
    answer_text: str = Field(min_length=1, max_length=500)


class AnswerSubmitResponse(BaseModel):
    is_correct: bool
    session_status: str
    current_stage_number: int
    message: str
    xp_awarded: int = 0
    new_badges: list[str] = []


class SessionSummary(BaseModel):
    id: uuid.UUID
    status: str
    expires_at: datetime
