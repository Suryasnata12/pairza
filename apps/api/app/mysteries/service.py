import random
import re
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.mysteries.models import Mystery, MysteryStage
from app.sessions.models import UserMysteryHistory

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_answer(raw: str) -> str:
    """Case/whitespace/punctuation-insensitive so 'Iguazu Falls!' matches 'iguazu falls'."""
    cleaned = re.sub(r"[^\w\s]", "", raw.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def answer_matches(raw_answer: str, accepted_patterns: list[str]) -> bool:
    normalized = normalize_answer(raw_answer)
    return normalized in {normalize_answer(p) for p in accepted_patterns}


async def pick_random_mystery_for_pair(
    db: AsyncSession, user_a_id: uuid.UUID, user_b_id: uuid.UUID, cooldown_mystery_ids: set[uuid.UUID]
) -> Mystery | None:
    """
    Randomly selects a published mystery neither player has completed
    recently (spec section 3: "users do not repeatedly receive the same
    mystery"). Loads stages/clues eagerly since the caller needs the full
    tree to build the session.
    """
    query = (
        select(Mystery)
        .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
        .where(Mystery.is_published.is_(True))
    )
    if cooldown_mystery_ids:
        query = query.where(Mystery.id.not_in(cooldown_mystery_ids))

    result = await db.execute(query)
    candidates = list(result.scalars().all())

    # Each mystery needs at least one stage with both a player_a and a
    # player_b clue, or the session has nothing complementary to assign.
    candidates = [
        m for m in candidates
        if m.stages and all(
            {c.role for c in s.clues} >= {"player_a", "player_b"} for s in m.stages
        )
    ]

    if not candidates:
        return None
    return random.choice(candidates)


async def recent_mystery_ids_for_user(db: AsyncSession, user_id: uuid.UUID, cooldown_cutoff) -> set[uuid.UUID]:
    result = await db.execute(
        select(UserMysteryHistory.mystery_id).where(
            UserMysteryHistory.user_id == user_id,
            UserMysteryHistory.created_at >= cooldown_cutoff,
        )
    )
    return set(result.scalars().all())
