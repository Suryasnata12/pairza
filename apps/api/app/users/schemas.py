import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    """Achievement-focused, per spec section 10 — deliberately no follower/following counts."""

    user_id: uuid.UUID
    username: str
    avatar_url: str | None
    country_code: str
    xp: int
    mystery_count: int
    solved_count: int
    solve_rate: float
    current_streak: int
    longest_streak: int
    countries_encountered: list[str]
    categories_completed: list[str]
    average_solve_seconds: float | None
    badge_count: int = 0

    model_config = {"from_attributes": True}


class UpdateProfileRequest(BaseModel):
    avatar_url: str | None = None
    country_code: str | None = Field(default=None, min_length=2, max_length=2)


class UpdatePreferencesRequest(BaseModel):
    timezone_region: str | None = None
    language: str | None = None
    interests: list[str] | None = None
    puzzle_experience_level: str | None = None
    preferred_categories: list[str] | None = None
    notifications_enabled: bool | None = None


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_verified: bool
    is_admin: bool
    created_at: datetime
    profile: ProfileResponse

    model_config = {"from_attributes": True}
