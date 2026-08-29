import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base
from app.common.mixins import UUIDPrimaryKeyMixin


class Badge(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "badges"

    code: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. "FIRST_SOLVE"
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(300))
    icon: Mapped[str] = mapped_column(String(50))  # lucide-react icon name, resolved client-side
    criteria_type: Mapped[str] = mapped_column(String(50))  # see rewards/service.py BADGE_CHECKS
    criteria_value: Mapped[int] = mapped_column(Integer, default=1)


class UserBadge(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "user_badges"
    __table_args__ = (Index("ix_user_badges_user", "user_id", "badge_id", unique=True),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    badge_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("badges.id", ondelete="CASCADE"))
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Reward(Base, UUIDPrimaryKeyMixin):
    """Append-only XP ledger — Profile.xp is a denormalized cache of SUM(amount) for fast reads."""

    __tablename__ = "rewards"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_sessions.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(20), default="xp")  # xp | fragment
    amount: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(100))  # e.g. "mystery_solved", "speed_bonus", "streak_bonus"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
