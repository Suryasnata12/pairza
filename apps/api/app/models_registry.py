"""
Import every ORM model module here, once. SQLAlchemy's declarative Base
only knows about a table once its model class has been imported somewhere
in the process — this module is that "somewhere," imported by both
alembic/env.py (for autogenerate) and tests/conftest.py (for create_all).
"""
from app.common.database import Base  # noqa: F401

from app.users.models import User, Profile, UserPreferences, RefreshToken, UserDailyActivity  # noqa: F401
from app.moderation.models import Block, Report, MuteEntry  # noqa: F401
from app.mysteries.models import Mystery, MysteryStage, MysteryClue  # noqa: F401
from app.matchmaking.models import Match, MatchHistory  # noqa: F401
from app.sessions.models import (  # noqa: F401
    MysterySession,
    InvestigationEvidence,
    MysterySubmission,
    UserMysteryHistory,
    Memory,
)
from app.chat.models import Message  # noqa: F401
from app.rewards.models import Badge, UserBadge, Reward  # noqa: F401

__all__ = ["Base"]
