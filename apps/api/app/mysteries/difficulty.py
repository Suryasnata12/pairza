"""
Difficulty tiers and their gameplay time limits.

This is the ONE place in Pairza that knows how long a mystery lasts. Nothing
else may restate these numbers. Consumers import from here:

  - matchmaking/service.py   sets a new session's end time (`expires_at`)
  - sessions/service.py      expiring-warning window + the fields the API returns
  - mysteries/schemas.py     the valid difficulty range for create/update/generate
  - scripts/seed.py          demo history that respects each mystery's limit
  - scripts/*mystery*.py     the AI generator/validator prompts
  - the web app              never keeps its own copy: it renders `expires_at`,
                             `duration_seconds` and `time_limit_seconds` that
                             the API sends (see GET /api/mysteries/difficulty-levels)

To change a duration, edit `_TIERS` below and nothing else.

Deliberately stdlib-only, so it can be imported from anywhere (models, schemas,
scripts, tests) without dragging in the database or web layers.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class DifficultyTier:
    level: int
    time_limit_minutes: int
    style: str  # short, player-facing description of what this tier asks of a pair

    @property
    def time_limit(self) -> timedelta:
        return timedelta(minutes=self.time_limit_minutes)

    @property
    def time_limit_seconds(self) -> int:
        return self.time_limit_minutes * 60


_TIERS: tuple[DifficultyTier, ...] = (
    DifficultyTier(level=1, time_limit_minutes=5, style="Straightforward clues"),
    DifficultyTier(level=2, time_limit_minutes=10, style="Requires discussion"),
    DifficultyTier(level=3, time_limit_minutes=15, style="Multiple connected clues"),
    DifficultyTier(level=4, time_limit_minutes=20, style="Misleading / indirect clues"),
    DifficultyTier(level=5, time_limit_minutes=30, style="Complex deduction"),
)

# Read-only view, keyed by difficulty level.
DIFFICULTY_TIERS: Mapping[int, DifficultyTier] = MappingProxyType({t.level: t for t in _TIERS})

MIN_DIFFICULTY: int = min(DIFFICULTY_TIERS)
MAX_DIFFICULTY: int = max(DIFFICULTY_TIERS)

# The "expiring soon" heads-up fires when this fraction of a session's time
# limit is left: 1 minute on a 5-minute mystery, 6 minutes on a 30-minute one.
EXPIRING_WARNING_FRACTION: float = 0.2


def find_difficulty_tier(difficulty: int) -> DifficultyTier | None:
    """Lenient lookup — None for an unsupported level. Use where a bad row must not crash a listing."""
    return DIFFICULTY_TIERS.get(difficulty)


def get_difficulty_tier(difficulty: int) -> DifficultyTier:
    """Strict lookup — raises ValueError for an unsupported level."""
    tier = DIFFICULTY_TIERS.get(difficulty)
    if tier is None:
        raise ValueError(
            f"Unsupported difficulty {difficulty!r}: expected an integer from {MIN_DIFFICULTY} to {MAX_DIFFICULTY}."
        )
    return tier


def time_limit_for_difficulty(difficulty: int) -> timedelta:
    return get_difficulty_tier(difficulty).time_limit


def time_limit_seconds_for_difficulty(difficulty: int) -> int:
    return get_difficulty_tier(difficulty).time_limit_seconds


def session_end_time(started_at: datetime, difficulty: int) -> datetime:
    """When a session that starts at `started_at` on a mystery of this difficulty must end."""
    return started_at + time_limit_for_difficulty(difficulty)


def expiring_warning_window(time_limit: timedelta) -> timedelta:
    """How long before the deadline the one-time `session.expiring` warning fires."""
    return time_limit * EXPIRING_WARNING_FRACTION


# Upper bounds across every tier — lets the background sweeper narrow its
# query in SQL before applying each session's own (per-tier) window in Python.
MAX_TIME_LIMIT: timedelta = max(t.time_limit for t in _TIERS)
MAX_EXPIRING_WARNING_WINDOW: timedelta = expiring_warning_window(MAX_TIME_LIMIT)
