"""
Adaptive difficulty: how a matched pair's rank turns into which difficulty
tier they play, and how a solve moves rank afterward.

Approved product rules (this module is their only implementation):

  1. PAIR DIFFICULTY = min(rank_a, rank_b). The lower-ranked player sets the
     normal ceiling for the pair — a Rank 2 + Rank 4 pair plays at Level 2
     by default. This is deliberate: matchmaking pairs strangers, and one
     player's clue is useless without the other's, so a pair that is in over
     its head fails together regardless of which one struggled.
  2. SURPRISE: on top of that base, SURPRISE_RULES can occasionally push the
     target higher (never lower) as a "skill test." Independent rolls, first
     match wins; tuned so most encounters stay at the base difficulty.
  3. NO DEMOTION (v1): failing an encounter, surprise or not, never lowers
     rank — see rank_after_solve. Only a solve can raise it.

`roll_target_difficulty` takes an explicit `random.Random` — never the
global `random` module — so a seeded instance makes tests and any future
analysis fully reproducible. Everything here is synchronous and free of
database or web-framework imports, so it can be tested in complete
isolation from the rest of the app.
"""
import random
from dataclasses import dataclass

from app.mysteries.difficulty import MAX_DIFFICULTY, MIN_DIFFICULTY

# New players, and any row without a computed rank yet, start here.
DEFAULT_DIFFICULTY_RANK: int = MIN_DIFFICULTY


@dataclass(frozen=True)
class SurpriseRule:
    """From the pair's base difficulty, with probability `chance`, jump forward `levels_up` levels instead."""

    levels_up: int
    chance: float


# Rolled in order, each independent of the others; the first one that hits wins.
# Tuned so a typical pair mostly gets its base difficulty: ~73% of the time nothing
# fires, ~20% they get one level up, ~7% a two-level "skill test", ~3% a rare three-
# level one. Not exposed to players; change these numbers to rebalance.
SURPRISE_RULES: tuple[SurpriseRule, ...] = (
    SurpriseRule(levels_up=1, chance=0.20),
    SurpriseRule(levels_up=2, chance=0.07),
    SurpriseRule(levels_up=3, chance=0.03),
)


def base_difficulty_for_pair(rank_a: int, rank_b: int) -> int:
    """The pair's normal ceiling before any surprise roll: the weaker player's rank.
    Clamped to the defined range so a bad or legacy row can't push selection out of bounds."""
    return max(MIN_DIFFICULTY, min(MAX_DIFFICULTY, min(rank_a, rank_b)))


def roll_target_difficulty(base_difficulty: int, rng: random.Random) -> int:
    """Applies SURPRISE_RULES on top of `base_difficulty`. `rng` is required (no default,
    no global `random` fallback) precisely so a caller can never forget to make this testable."""
    for rule in SURPRISE_RULES:
        if rng.random() < rule.chance:
            return min(MAX_DIFFICULTY, base_difficulty + rule.levels_up)
    return base_difficulty


def rank_after_solve(current_rank: int, mystery_difficulty: int) -> int:
    """
    The only place rank changes. No demotion in this version: a loss (see
    rewards.service.process_non_solve, which never calls this) leaves rank
    exactly where it was, surprise-challenge loss included.

    Solving a mystery AT OR ABOVE the player's current rank is evidence
    they're ready for more, so rank moves up by exactly one level — never
    straight to the mystery's own difficulty, so a single lucky high-level
    surprise solve can't vault someone from Rank 1 to Rank 5 in one step;
    repeated success is what climbs the ladder ("1 -> 2 -> 3 -> 4 -> 5",
    never a skip). Solving something BELOW the player's current rank (e.g.
    a warm-up mystery the pool happened to offer) doesn't demonstrate
    anything new and leaves rank unchanged.
    """
    if mystery_difficulty < current_rank:
        return current_rank
    return min(MAX_DIFFICULTY, current_rank + 1)
