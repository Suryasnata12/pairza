import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Auth-critical identity. Public/gameplay-facing data lives on Profile."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False)
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    date_of_birth: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    profile: Mapped["Profile"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    preferences: Mapped["UserPreferences"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class Profile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Public, achievement-focused profile. Deliberately has no follower/friend counts."""

    __tablename__ = "profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    country_code: Mapped[str] = mapped_column(String(2))  # ISO 3166-1 alpha-2, drives the flag emoji

    xp: Mapped[int] = mapped_column(Integer, default=0)
    mystery_count: Mapped[int] = mapped_column(Integer, default=0)
    solved_count: Mapped[int] = mapped_column(Integer, default=0)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_active_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    countries_encountered: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    categories_completed: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    average_solve_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    user: Mapped["User"] = relationship(back_populates="profile")

    @property
    def solve_rate(self) -> float:
        if self.mystery_count == 0:
            return 0.0
        return round(self.solved_count / self.mystery_count, 4)


class UserPreferences(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Private, matchmaking-relevant preferences — never shown to a stranger directly."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )

    timezone_region: Mapped[str] = mapped_column(String(64), default="UTC")
    language: Mapped[str] = mapped_column(String(8), default="en")
    interests: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    puzzle_experience_level: Mapped[str] = mapped_column(String(16), default="beginner")
    preferred_categories: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    notifications_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="preferences")


class RefreshToken(Base, UUIDPrimaryKeyMixin):
    """Stores only a hash of the refresh token's jti, so a DB leak can't be replayed."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserDailyActivity(Base, UUIDPrimaryKeyMixin):
    """
    One row per user per calendar day they were seen using the app — the
    entire foundation DAU/MAU/retention are computed from. Populated by a
    background task attached to get_current_user (see common/deps.py), so
    recording activity never adds latency to the request that triggered it.

    `activity_date` is a Date, not a DateTime — we only ever care about
    "which calendar day," never the time, and the unique index on
    (user_id, activity_date) means recording the same user twice in one
    day is a cheap no-op (ON CONFLICT DO NOTHING) rather than a duplicate row.
    """

    __tablename__ = "user_daily_activity"
    __table_args__ = (Index("ix_user_daily_activity_unique", "user_id", "activity_date", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    activity_date: Mapped[date] = mapped_column(Date, index=True)
