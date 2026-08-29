import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import UUIDPrimaryKeyMixin

# Authoritative session lifecycle (spec section 14).
SESSION_STATUSES = ["WAITING", "ACTIVE", "SOLVED", "FAILED", "EXPIRED", "CANCELLED"]
TERMINAL_STATUSES = {"SOLVED", "FAILED", "EXPIRED", "CANCELLED"}


class MysterySession(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "mystery_sessions"
    __table_args__ = (
        Index("ix_sessions_status_expires", "status", "expires_at"),
        Index("ix_sessions_player_a", "player_a_id"),
        Index("ix_sessions_player_b", "player_b_id"),
    )

    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"))
    mystery_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mysteries.id"))

    player_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    player_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))

    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    current_stage_number: Mapped[int] = mapped_column(Integer, default=1)

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)  # started_at + 24h, backend-computed, never trusted from client
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expiring_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    evidence: Mapped[list["InvestigationEvidence"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    submissions: Mapped[list["MysterySubmission"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    def role_for(self, user_id: uuid.UUID) -> str | None:
        if user_id == self.player_a_id:
            return "player_a"
        if user_id == self.player_b_id:
            return "player_b"
        return None

    def partner_id(self, user_id: uuid.UUID) -> uuid.UUID | None:
        if user_id == self.player_a_id:
            return self.player_b_id
        if user_id == self.player_b_id:
            return self.player_a_id
        return None


class InvestigationEvidence(Base, UUIDPrimaryKeyMixin):
    """A pinned piece of the shared investigation board — either player can add these."""

    __tablename__ = "investigation_evidence"

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_sessions.id", ondelete="CASCADE"))
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped["MysterySession"] = relationship(back_populates="evidence")


class MysterySubmission(Base, UUIDPrimaryKeyMixin):
    """Every answer attempt, correct or not — gives us an audit trail and speed-solver stats."""

    __tablename__ = "mystery_submissions"
    __table_args__ = (Index("ix_submissions_session", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_sessions.id", ondelete="CASCADE"))
    stage_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_stages.id"), nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    answer_text: Mapped[str] = mapped_column(String(500))
    is_correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    session: Mapped["MysterySession"] = relationship(back_populates="submissions")


class UserMysteryHistory(Base, UUIDPrimaryKeyMixin):
    """One row per (user, completed session) — powers 'don't repeat this mystery' and profile stats."""

    __tablename__ = "user_mystery_history"
    __table_args__ = (Index("ix_history_user_mystery", "user_id", "mystery_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    mystery_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mysteries.id"))
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_sessions.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(32))
    result: Mapped[str] = mapped_column(String(16))  # solved | failed | expired
    solve_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Memory(Base, UUIDPrimaryKeyMixin):
    """A single user's keepsake of a completed connection. One row per participant per session."""

    __tablename__ = "memories"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_sessions.id", ondelete="CASCADE"))
    mystery_title: Mapped[str] = mapped_column(String(200))
    partner_country_code: Mapped[str] = mapped_column(String(2))
    solved: Mapped[bool] = mapped_column(Boolean)
    solve_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    anonymous_message: Mapped[str | None] = mapped_column(String(280), nullable=True)
    day_number: Mapped[int] = mapped_column(Integer)  # this user's Nth completed Pairza day, for the "DAY 047" display
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
