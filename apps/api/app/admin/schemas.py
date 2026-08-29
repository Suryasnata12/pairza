import uuid
from datetime import datetime

from pydantic import BaseModel


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


class AnalyticsOut(BaseModel):
    total_users: int
    active_sessions: int
    mysteries_completed_total: int
    mysteries_solved_total: int
    completion_rate: float
    average_solve_seconds: float | None
    category_breakdown: dict[str, int]
    open_reports: int
