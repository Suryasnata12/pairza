import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.deps import get_current_user
from app.common.exceptions import NotFoundError
from app.mysteries.difficulty import DIFFICULTY_TIERS
from app.mysteries.models import Mystery
from app.mysteries.schemas import DifficultyLevelOut, MysteryTeaser
from app.sessions.models import MysterySession
from app.users.models import User

router = APIRouter(prefix="/api/mysteries", tags=["mysteries"])


@router.get("/today", response_model=MysteryTeaser | None)
async def get_todays_mystery(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    Powers the Home screen's 'TODAY'S MYSTERY' card. Returns only the
    spoiler-safe teaser (category, difficulty, one-line summary) for the
    user's current WAITING/ACTIVE session — never the clue itself. Returns
    null if the user hasn't started today's experience yet, which the
    frontend renders as the 'YOUR NEXT EXPERIENCE IS READY' empty state.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status.in_(["WAITING", "ACTIVE"]),
            MysterySession.expires_at > now,
            (MysterySession.player_a_id == user.id) | (MysterySession.player_b_id == user.id),
        )
    )
    session = result.scalars().first()
    if not session:
        return None

    mystery_result = await db.execute(select(Mystery).where(Mystery.id == session.mystery_id))
    mystery = mystery_result.scalar_one()
    return MysteryTeaser.model_validate(mystery)


@router.get("/difficulty-levels", response_model=list[DifficultyLevelOut])
async def list_difficulty_levels(user: User = Depends(get_current_user)):
    """
    The difficulty -> time-limit table straight from mysteries/difficulty.py, so
    clients (e.g. the admin panel's difficulty picker) show real values instead
    of keeping their own copy. Declared before "/{mystery_id}" on purpose.
    """
    return [
        DifficultyLevelOut(
            difficulty=t.level, time_limit_minutes=t.time_limit_minutes,
            time_limit_seconds=t.time_limit_seconds, style=t.style,
        )
        for t in DIFFICULTY_TIERS.values()
    ]


@router.get("/{mystery_id}", response_model=MysteryTeaser)
async def get_mystery_teaser(mystery_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Spoiler-safe lookup by id — used for e.g. Memory Vault entries linking back to a mystery's summary."""
    result = await db.execute(select(Mystery).where(Mystery.id == mystery_id))
    mystery = result.scalar_one_or_none()
    if not mystery:
        raise NotFoundError("This mystery disappeared into the unknown.")
    return MysteryTeaser.model_validate(mystery)
