import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.database import Base
from app.common.mixins import TimestampMixin, UUIDPrimaryKeyMixin

# Registry of mystery categories (spec section 12). Adding a new category is
# a one-line addition here plus content — it never requires touching
# matchmaking, session, or chat code, which is the "extensible without
# changing the core application" requirement.
MYSTERY_CATEGORIES = [
    "internet_hunt",
    "visual",
    "geo",
    "audio",
    "logic",
    "cipher",
    "investigation",
    "pattern",
    "arg",
]

CLUE_ROLES = ["player_a", "player_b"]


class Mystery(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "mysteries"
    __table_args__ = (Index("ix_mysteries_published_category", "is_published", "category"),)

    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(32), index=True)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1-5, rendered as dots in the UI
    summary: Mapped[str] = mapped_column(Text)  # short, spoiler-free teaser shown before reveal
    flavor_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # shown during reveal animation

    # Normalized accepted answers for the final stage, e.g. ["iguazu falls", "iguacu falls"].
    # Matching is case/whitespace-insensitive — see mysteries/service.py normalize_answer().
    final_answer_patterns: Mapped[list[str]] = mapped_column(ARRAY(String))

    is_published: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    stages: Mapped[list["MysteryStage"]] = relationship(
        back_populates="mystery", cascade="all, delete-orphan", order_by="MysteryStage.stage_number"
    )


class MysteryStage(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "mystery_stages"
    __table_args__ = (Index("ix_stages_mystery_number", "mystery_id", "stage_number", unique=True),)

    mystery_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mysteries.id", ondelete="CASCADE"))
    stage_number: Mapped[int] = mapped_column(Integer)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)  # narrative framing shown when the stage unlocks

    # A stage may require a checkpoint answer before advancing to the next stage.
    # Null on the final stage, whose "answer" is the mystery's final_answer_patterns.
    checkpoint_answer_patterns: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)

    mystery: Mapped["Mystery"] = relationship(back_populates="stages")
    clues: Mapped[list["MysteryClue"]] = relationship(back_populates="stage", cascade="all, delete-orphan")


class MysteryClue(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "mystery_clues"
    __table_args__ = (Index("ix_clues_stage_role", "stage_id", "role"),)

    stage_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("mystery_stages.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # player_a | player_b — complementary, never identical
    text: Mapped[str] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    stage: Mapped["MysteryStage"] = relationship(back_populates="clues")
