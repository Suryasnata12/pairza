"""
The difficulty -> time-limit table is a product rule. These tests restate it independently of
app/mysteries/difficulty.py, so changing a duration is a deliberate two-place edit (config + this
file) rather than something that can drift unnoticed.

The first group needs no database; the schema group needs only pydantic.
"""
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.admin.schemas import GenerateMysteriesRequest
from app.mysteries import difficulty
from app.mysteries.schemas import MysteryCandidate, MysteryCreate, MysteryUpdate

EXPECTED_MINUTES = {1: 5, 2: 10, 3: 15, 4: 20, 5: 30}
EXPECTED_STYLES = {
    1: "Straightforward clues",
    2: "Requires discussion",
    3: "Multiple connected clues",
    4: "Misleading / indirect clues",
    5: "Complex deduction",
}


@pytest.mark.parametrize("level,minutes", sorted(EXPECTED_MINUTES.items()))
def test_each_difficulty_maps_to_its_exact_duration(level, minutes):
    assert difficulty.time_limit_for_difficulty(level) == timedelta(minutes=minutes)
    assert difficulty.time_limit_seconds_for_difficulty(level) == minutes * 60


def test_challenge_styles_match_the_spec():
    assert {t.level: t.style for t in difficulty.DIFFICULTY_TIERS.values()} == EXPECTED_STYLES


def test_there_are_exactly_five_tiers_and_the_bounds_follow_them():
    assert sorted(difficulty.DIFFICULTY_TIERS) == [1, 2, 3, 4, 5]
    assert (difficulty.MIN_DIFFICULTY, difficulty.MAX_DIFFICULTY) == (1, 5)


def test_time_limits_increase_with_difficulty():
    limits = [difficulty.time_limit_for_difficulty(level) for level in range(1, 6)]
    assert limits == sorted(limits) and len(set(limits)) == 5


@pytest.mark.parametrize("bad", [0, 6, -1, 99, None])
def test_unsupported_difficulty_is_rejected_by_the_strict_helper(bad):
    with pytest.raises(ValueError):
        difficulty.get_difficulty_tier(bad)
    with pytest.raises(ValueError):
        difficulty.time_limit_for_difficulty(bad)
    assert difficulty.find_difficulty_tier(bad) is None  # the lenient lookup never raises


def test_session_end_time_is_start_plus_the_limit():
    start = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
    assert difficulty.session_end_time(start, 1) == start + timedelta(minutes=5)
    assert difficulty.session_end_time(start, 5) == start + timedelta(minutes=30)


def test_the_tier_table_cannot_be_mutated_at_runtime():
    with pytest.raises(TypeError):
        difficulty.DIFFICULTY_TIERS[6] = difficulty.DIFFICULTY_TIERS[5]  # type: ignore[index]


def test_expiring_warning_window_is_a_fifth_of_the_time_limit():
    assert difficulty.expiring_warning_window(timedelta(minutes=5)) == timedelta(minutes=1)
    assert difficulty.expiring_warning_window(timedelta(minutes=30)) == timedelta(minutes=6)
    assert difficulty.MAX_EXPIRING_WARNING_WINDOW == timedelta(minutes=6)


# --- every schema that accepts a difficulty uses the same central bounds ---------------------------

_MYSTERY_KWARGS = dict(title="A title", category="geo", summary="A summary long enough.", final_answer_patterns=["x"])


@pytest.mark.parametrize("bad", [0, 6])
def test_schemas_reject_a_difficulty_outside_the_defined_tiers(bad):
    with pytest.raises(ValidationError):
        MysteryCreate(difficulty=bad, stages=[], **_MYSTERY_KWARGS)
    with pytest.raises(ValidationError):
        MysteryUpdate(difficulty=bad)
    with pytest.raises(ValidationError):
        GenerateMysteriesRequest(difficulty=bad)
    with pytest.raises(ValidationError):
        MysteryCandidate(difficulty=bad, stages=[], **_MYSTERY_KWARGS)


@pytest.mark.parametrize("good", [1, 2, 3, 4, 5])
def test_schemas_accept_every_defined_tier(good):
    assert MysteryCreate(difficulty=good, stages=[], **_MYSTERY_KWARGS).difficulty == good
    assert MysteryUpdate(difficulty=good).difficulty == good
    assert GenerateMysteriesRequest(difficulty=good).difficulty == good
