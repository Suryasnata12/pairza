"""
Adaptive difficulty (app/mysteries/progression.py). Pure functions, no
database — these are the specific rules approved for the production
difficulty system, restated as tests so a later edit can't drift from them
unnoticed:

  - pair difficulty = min(rank_a, rank_b)
  - surprise can push the target higher, never lower, and only sometimes
  - no demotion in v1: only rank_after_solve can move rank, and only upward
"""
import random
from collections import Counter

import pytest

from app.mysteries.difficulty import MAX_DIFFICULTY, MIN_DIFFICULTY
from app.mysteries.progression import (
    SURPRISE_RULES,
    base_difficulty_for_pair,
    rank_after_solve,
    roll_target_difficulty,
)


# --- Rank 2 + Rank 4 -> base difficulty 2 --------------------------------------------------

def test_pair_base_difficulty_is_the_lower_ranked_players_level():
    assert base_difficulty_for_pair(2, 4) == 2
    assert base_difficulty_for_pair(4, 2) == 2  # order-independent


@pytest.mark.parametrize("rank_a,rank_b,expected", [(1, 1, 1), (3, 3, 3), (5, 5, 5), (1, 5, 1), (5, 1, 1)])
def test_pair_base_difficulty_matrix(rank_a, rank_b, expected):
    assert base_difficulty_for_pair(rank_a, rank_b) == expected


def test_pair_base_difficulty_clamps_an_out_of_range_rank():
    """Only reachable via hand-edited data, but selection must never crash on it."""
    assert base_difficulty_for_pair(0, 3) == MIN_DIFFICULTY
    assert base_difficulty_for_pair(9, 3) == 3
    assert base_difficulty_for_pair(9, 9) == MAX_DIFFICULTY


# --- Surprise challenge may exceed the base ceiling only when the surprise rule allows it ------

def test_roll_target_difficulty_is_reproducible_from_a_seed():
    a = [roll_target_difficulty(2, random.Random(7)) for _ in range(200)]
    b = [roll_target_difficulty(2, random.Random(7)) for _ in range(200)]
    assert a == b


def test_roll_target_difficulty_never_goes_below_the_base():
    rng = random.Random(1)
    for _ in range(5000):
        assert roll_target_difficulty(2, rng) >= 2


def test_roll_target_difficulty_never_exceeds_max_difficulty():
    rng = random.Random(2)
    for _ in range(5000):
        assert roll_target_difficulty(4, rng) <= MAX_DIFFICULTY
    assert roll_target_difficulty(MAX_DIFFICULTY, random.Random(3)) == MAX_DIFFICULTY


def test_surprise_can_push_above_the_base_but_stays_rare():
    """The whole point of the mechanic: 'occasionally' higher, not 'often'."""
    rng = random.Random(42)
    rolls = [roll_target_difficulty(2, rng) for _ in range(200_000)]
    counts = Counter(rolls)
    total = len(rolls)

    assert counts[2] > 0 and any(counts[d] > 0 for d in (3, 4, 5))  # both the base AND a surprise happen
    assert counts[2] / total > 0.65  # base difficulty is still the common outcome
    assert counts.get(5, 0) / total < 0.05  # the rare 2-up-plus-1-up combination stays rare


def test_a_base_of_five_can_never_be_exceeded_by_a_surprise():
    rng = random.Random(9)
    assert all(roll_target_difficulty(MAX_DIFFICULTY, rng) == MAX_DIFFICULTY for _ in range(1000))


def test_surprise_rules_are_configured_as_documented():
    """Pins the current tuning so a silent edit to it is visible in a diff."""
    assert [(r.levels_up, r.chance) for r in SURPRISE_RULES] == [(1, 0.20), (2, 0.07), (3, 0.03)]


# --- Successful higher-level challenge -> progression can increase -----------------------------

def test_solving_at_current_rank_advances_by_one_level():
    """This is what makes NORMAL play climb the ladder — not just rare surprises."""
    assert rank_after_solve(1, 1) == 2
    assert rank_after_solve(3, 3) == 4


def test_solving_a_surprise_challenge_above_rank_advances_by_only_one_level():
    """A lucky high-level surprise solve doesn't vault a player straight to that difficulty —
    repeated success is what climbs the ladder, one level per solve."""
    assert rank_after_solve(2, 5) == 3
    assert rank_after_solve(1, 4) == 2


def test_rank_cannot_exceed_max_difficulty():
    assert rank_after_solve(MAX_DIFFICULTY, MAX_DIFFICULTY) == MAX_DIFFICULTY
    assert rank_after_solve(4, 5) == 5


def test_solving_below_current_rank_leaves_rank_unchanged():
    """Doesn't demonstrate anything new — and this is NOT a demotion path either way."""
    assert rank_after_solve(4, 2) == 4
    assert rank_after_solve(3, 1) == 3


# --- Normal failure / surprise failure -> rank unchanged ----------------------------------------
# rank_after_solve is the ONLY function that changes rank at all (see rewards/service.py:
# process_non_solve never calls it). So "a failure never changes rank" is really the statement
# that no failure path calls this function — proven at the rewards-service layer in
# test_rewards.py's difficulty-rank tests, not here in the pure module. What IS provable here is
# that this function itself has no code path that can lower rank, from ANY inputs:

@pytest.mark.parametrize("current_rank", [1, 2, 3, 4, 5])
@pytest.mark.parametrize("mystery_difficulty", [1, 2, 3, 4, 5])
def test_rank_after_solve_never_decreases_for_any_input(current_rank, mystery_difficulty):
    assert rank_after_solve(current_rank, mystery_difficulty) >= current_rank
