import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base
from app.common.mixins import UUIDPrimaryKeyMixin


class Match(Base, UUIDPrimaryKeyMixin):
    """One pairing event. A Match always produces exactly one MysterySession."""

    __tablename__ = "matches"

    user_a_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    user_b_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    mystery_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mysteries.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MatchHistory(Base, UUIDPrimaryKeyMixin):
    """Denormalized, symmetric log of who has been paired with whom and when.

    Written twice per Match (once per direction) so "has X met Y in the last
    N days" is a single indexed lookup instead of an OR-query across two
    columns — this is the query the matchmaker runs on every single pairing
    attempt, so it needs to be cheap.
    """

    __tablename__ = "match_history"
    __table_args__ = (Index("ix_match_history_pair", "user_id", "matched_with_user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    matched_with_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    match_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("matches.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
