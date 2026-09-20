import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.mysteries.difficulty import MAX_DIFFICULTY, MIN_DIFFICULTY


class AdminUserOut(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    country_code: str
    is_active: bool
    is_suspended: bool
    is_banned: bool
    is_admin: bool
    created_at: datetime
    mystery_count: int
    solved_count: int

    model_config = {"from_attributes": True}


class SuspendUserRequest(BaseModel):
    reason: str


class ReportReviewRequest(BaseModel):
    status: str  # reviewed | actioned | dismissed


class ActiveSessionOut(BaseModel):
    id: uuid.UUID
    status: str
    mystery_title: str
    category: str
    current_stage_number: int
    started_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class DailyCount(BaseModel):
    date: str
    count: int


class AnalyticsOut(BaseModel):
    total_users: int
    active_sessions: int
    mysteries_completed_total: int
    mysteries_solved_total: int
    completion_rate: float
    average_solve_seconds: float | None
    category_breakdown: dict[str, int]
    open_reports: int

    # Engagement (see admin/service.py's engagement-metrics functions for
    # exactly how each of these is computed and why).
    dau: int
    mau: int
    d1_retention: float | None
    d7_retention: float | None
    d30_retention: float | None
    matches_per_user: float
    games_completed_per_user: float
    average_session_length_seconds: float | None
    dau_trend: list[DailyCount]


# --- Mystery generation pipeline admin controls ---

class CategoryConfigOut(BaseModel):
    category: str
    is_enabled: bool
    published_count: int
    draft_count: int


class CategoryPoolCountsOut(BaseModel):
    categories: list[CategoryConfigOut]


class GenerateMysteriesRequest(BaseModel):
    category: str | None = None  # None + all_categories=True means every category
    all_categories: bool = False
    quantity: int = Field(default=5, ge=1, le=50)
    difficulty: int | None = Field(default=None, ge=MIN_DIFFICULTY, le=MAX_DIFFICULTY)


class GenerationJobStatusOut(BaseModel):
    status: str  # "idle" | "running" | "done" | "failed"
    started_at: str | None = None
    finished_at: str | None = None
    report: list[dict] | None = None
    error: str | None = None
