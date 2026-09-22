import random
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.mysteries.difficulty import MAX_DIFFICULTY, MIN_DIFFICULTY
from app.mysteries.progression import DEFAULT_DIFFICULTY_RANK, base_difficulty_for_pair, roll_target_difficulty
from app.mysteries.models import Mystery, MysteryCategoryConfig, MysteryStage
from app.sessions.models import UserMysteryHistory

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_answer(raw: str) -> str:
    """Case/whitespace/punctuation-insensitive so 'Iguazu Falls!' matches 'iguazu falls'."""
    cleaned = re.sub(r"[^\w\s]", "", raw.lower())
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


def answer_matches(raw_answer: str, accepted_patterns: list[str]) -> bool:
    normalized = normalize_answer(raw_answer)
    return normalized in {normalize_answer(p) for p in accepted_patterns}


async def _disabled_categories(db: AsyncSession) -> set[str]:
    """Absence of a config row means ENABLED (see MysteryCategoryConfig's
    own docstring) — only explicit is_enabled=False rows count here."""
    result = await db.execute(select(MysteryCategoryConfig.category).where(MysteryCategoryConfig.is_enabled.is_(False)))
    return set(result.scalars().all())


async def _last_played_categories(db: AsyncSession, user_a_id: uuid.UUID, user_b_id: uuid.UUID) -> set[str]:
    """Each player's most recent category, so today's pick can lean toward
    something neither of them just did — a soft nudge toward variety, not
    a hard exclusion (with only 9 categories and a small mystery pool, a
    hard rule could too easily leave zero eligible mysteries)."""
    result = await db.execute(
        select(UserMysteryHistory.user_id, UserMysteryHistory.category)
        .where(UserMysteryHistory.user_id.in_([user_a_id, user_b_id]))
        .order_by(UserMysteryHistory.created_at.desc())
    )
    seen_for: set[uuid.UUID] = set()
    categories: set[str] = set()
    for uid, category in result.all():
        if uid not in seen_for:
            categories.add(category)
            seen_for.add(uid)
        if len(seen_for) == 2:
            break
    return categories


async def pick_random_mystery_for_pair(
    db: AsyncSession, user_a_id: uuid.UUID, user_b_id: uuid.UUID, cooldown_mystery_ids: set[uuid.UUID],
    rank_a: int = DEFAULT_DIFFICULTY_RANK, rank_b: int = DEFAULT_DIFFICULTY_RANK,
    rng: Optional[random.Random] = None,
) -> Mystery | None:
    """
    Selects a published mystery neither player has completed recently
    (spec section 3: "users do not repeatedly receive the same mystery"),
    excludes any category an admin has disabled, and softly prefers a
    category different from either player's most recent mystery for a bit
    of day-to-day variety. Loads stages/clues eagerly since the caller
    needs the full tree to build the session.

    DIFFICULTY (mysteries/progression.py): the pair's base difficulty is
    min(rank_a, rank_b) — the weaker player sets the normal ceiling — with an
    occasional "surprise" roll pushing it higher. This is a SOFT target, the
    same way category freshness is: candidates at the target difficulty are
    preferred, but with today's small hand-authored pool a tier may simply
    have no mysteries yet, so selection falls back rather than stalling
    matchmaking (see the three-step fallback below).

    `rng` defaults to a fresh `random.Random()` per call — NOT the seeded
    module-level `random` used for the final pool.choice — so tests can pass
    a seeded instance for a reproducible roll while normal calls need no
    special setup.
    """
    rng = rng or random.Random()
    disabled = await _disabled_categories(db)

    query = (
        select(Mystery)
        .options(selectinload(Mystery.stages).selectinload(MysteryStage.clues))
        .where(
            Mystery.is_published.is_(True),
            # A mystery whose difficulty has no defined time limit can't be given a session
            # end time, so it's never eligible (guards hand-edited / legacy rows).
            Mystery.difficulty.between(MIN_DIFFICULTY, MAX_DIFFICULTY),
        )
    )
    if cooldown_mystery_ids:
        query = query.where(Mystery.id.not_in(cooldown_mystery_ids))
    if disabled:
        query = query.where(Mystery.category.not_in(disabled))

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

    target_difficulty = roll_target_difficulty(base_difficulty_for_pair(rank_a, rank_b), rng)

    # Three-step difficulty fallback, each step only used if the one before it is empty:
    #   1. exactly the target difficulty (the common case once the pool has grown)
    #   2. the hardest available difficulty AT OR BELOW the target (a surprise 5 with
    #      nothing above 2 in the pool yet should never round UP past what was rolled)
    #   3. the full candidate pool regardless of difficulty (something beats WAITING)
    exact = [m for m in candidates if m.difficulty == target_difficulty]
    if exact:
        difficulty_pool = exact
    else:
        at_or_below = [m for m in candidates if m.difficulty <= target_difficulty]
        difficulty_pool = [m for m in at_or_below if m.difficulty == max(c.difficulty for c in at_or_below)] \
            if at_or_below else candidates

    recent_categories = await _last_played_categories(db, user_a_id, user_b_id)
    fresh_category_candidates = [m for m in difficulty_pool if m.category not in recent_categories]

    # Prefer variety, but never let it produce a WAITING result when a
    # same-category mystery was actually available — falling back to the
    # full (difficulty-filtered) pool beats leaving two matched players
    # without a mystery at all.
    pool = fresh_category_candidates if fresh_category_candidates else difficulty_pool
    return rng.choice(pool)


async def recent_mystery_ids_for_user(db: AsyncSession, user_id: uuid.UUID, cooldown_cutoff) -> set[uuid.UUID]:
    result = await db.execute(
        select(UserMysteryHistory.mystery_id).where(
            UserMysteryHistory.user_id == user_id,
            UserMysteryHistory.created_at >= cooldown_cutoff,
        )
    )
    return set(result.scalars().all())
