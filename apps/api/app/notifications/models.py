import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.common.database import Base
from app.common.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)

class PushSubscription(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A browser/device subscription for Web Push notifications."""

    __tablename__ = "push_subscriptions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The endpoint is needed to send notifications. Its hash provides
    # a compact unique identifier without indexing a long URL.
    endpoint: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )

    endpoint_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    p256dh_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    auth_key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

class PushReminderLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "push_reminder_logs"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "reminder_date",
            "reminder_type",
            name="uq_push_reminder_user_date_type",
        ),
        Index("ix_push_reminder_logs_status", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The user's local calendar date, not the UTC date.
    reminder_date: Mapped[date] = mapped_column(Date, nullable=False)

    reminder_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="streak"
    )

    # pending, sent, or failed
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending"
    )

    attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    last_error: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )