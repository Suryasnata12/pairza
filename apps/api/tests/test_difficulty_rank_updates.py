"""
Adaptive difficulty, exercised through the REAL solve/non-solve flow (not just
the pure functions in test_difficulty_progression.py): does profile.difficulty_rank
actually move the way the approved rules say it should once a session ends.

  - Normal failure -> rank unchanged
  - Surprise failure -> rank unchanged
  - Successful higher-level challenge -> progression can increase
"""
from sqlalchemy import select

from app.rewards import service as rewards_service
from app.users.models import Profile
from tests.conftest import make_mystery, make_user
from tests.test_sessions import _create_session_directly


async def _rank_of(db, user_id) -> int:
    result = await db.execute(select(Profile.difficulty_rank).where(Profile.user_id == user_id))
    return result.scalar_one()


async def test_new_profile_starts_at_rank_one(db):
    user = await make_user(db, "rankstart@test.com", "rankstart")
    assert await _rank_of(db, user.id) == 1


async def test_normal_failure_leaves_rank_unchanged(db):
    """An ordinary loss at the player's own level: no demotion, and no advancement either."""
    mystery = await make_mystery(db, difficulty=2)
    user_a = await make_user(db, "nf_a@test.com", "nf_a", difficulty_rank=2)
    user_b = await make_user(db, "nf_b@test.com", "nf_b", difficulty_rank=2)
    session = await _create_session_directly(db, mystery, user_a, user_b)

    await rewards_service.process_non_solve(db, session, mystery, "failed")

    assert await _rank_of(db, user_a.id) == 2
    assert await _rank_of(db, user_b.id) == 2


async def test_surprise_challenge_failure_leaves_rank_unchanged(db):
    """The specific rule the product brief calls out: failing a SURPRISE (above-rank) challenge
    must not demote either — a rank-1 player who fails a difficulty-4 surprise stays rank 1,
    not dropped or penalized in any way."""
    surprise_mystery = await make_mystery(db, difficulty=4)
    user_a = await make_user(db, "sf_a@test.com", "sf_a", difficulty_rank=1)
    user_b = await make_user(db, "sf_b@test.com", "sf_b", difficulty_rank=1)
    session = await _create_session_directly(db, surprise_mystery, user_a, user_b)

    await rewards_service.process_non_solve(db, session, surprise_mystery, "failed")

    assert await _rank_of(db, user_a.id) == 1
    assert await _rank_of(db, user_b.id) == 1


async def test_expiring_a_surprise_challenge_also_leaves_rank_unchanged(db):
    """Timing out is a distinct outcome from failing (see sessions/service.py's TIMES_UP path),
    and must be equally penalty-free for rank."""
    surprise_mystery = await make_mystery(db, difficulty=5)
    user_a = await make_user(db, "exp_a@test.com", "exp_a", difficulty_rank=2)
    session = await _create_session_directly(db, surprise_mystery, user_a, await make_user(db, "exp_b@test.com", "exp_b", difficulty_rank=2))

    await rewards_service.process_non_solve(db, session, surprise_mystery, "expired")

    assert await _rank_of(db, user_a.id) == 2


async def test_solving_at_current_rank_advances_progression(db):
    """The normal, day-to-day path a Rank-1 player climbs to Rank 2 through — not a surprise,
    just consistently solving mysteries at their own level."""
    mystery = await make_mystery(db, difficulty=1, final_answers=["correct answer"])
    user_a = await make_user(db, "adv_a@test.com", "adv_a", difficulty_rank=1)
    user_b = await make_user(db, "adv_b@test.com", "adv_b", difficulty_rank=1)
    session = await _create_session_directly(db, mystery, user_a, user_b)

    await sessions_service_submit_and_solve(db, session, user_a.id, "correct answer")

    assert await _rank_of(db, user_a.id) == 2
    assert await _rank_of(db, user_b.id) == 2  # both participants advance, not just whoever typed the answer


async def test_successful_surprise_challenge_increases_rank_by_one_level_not_to_the_mysterys_own_level(db):
    """Successful higher-level challenge -> progression can increase, but a single lucky solve of a
    difficulty-5 surprise only advances a Rank-1 player to Rank 2, not straight to 5 — repeated
    success is what climbs the ladder (see progression.rank_after_solve's own docstring)."""
    surprise_mystery = await make_mystery(db, difficulty=5, final_answers=["correct answer"])
    user_a = await make_user(db, "surp_a@test.com", "surp_a", difficulty_rank=1)
    user_b = await make_user(db, "surp_b@test.com", "surp_b", difficulty_rank=1)
    session = await _create_session_directly(db, surprise_mystery, user_a, user_b)

    await sessions_service_submit_and_solve(db, session, user_a.id, "correct answer")

    assert await _rank_of(db, user_a.id) == 2
    assert await _rank_of(db, user_b.id) == 2


async def test_solving_below_current_rank_does_not_advance_further(db):
    """A higher-ranked player solving an easy warm-up mystery: no new evidence of extra skill,
    so rank stays exactly where it was (this is NOT a demotion path — it's simply a no-op)."""
    easy_mystery = await make_mystery(db, difficulty=1, final_answers=["correct answer"])
    user_a = await make_user(db, "belowrank_a@test.com", "belowrank_a", difficulty_rank=4)
    user_b = await make_user(db, "belowrank_b@test.com", "belowrank_b", difficulty_rank=4)
    session = await _create_session_directly(db, easy_mystery, user_a, user_b)

    await sessions_service_submit_and_solve(db, session, user_a.id, "correct answer")

    assert await _rank_of(db, user_a.id) == 4
    assert await _rank_of(db, user_b.id) == 4


async def test_rank_never_exceeds_the_maximum_difficulty(db):
    mystery = await make_mystery(db, difficulty=5, final_answers=["correct answer"])
    user_a = await make_user(db, "maxrank_a@test.com", "maxrank_a", difficulty_rank=5)
    user_b = await make_user(db, "maxrank_b@test.com", "maxrank_b", difficulty_rank=5)
    session = await _create_session_directly(db, mystery, user_a, user_b)

    await sessions_service_submit_and_solve(db, session, user_a.id, "correct answer")

    assert await _rank_of(db, user_a.id) == 5


# --- helper -------------------------------------------------------------------------------------

async def sessions_service_submit_and_solve(db, session, user_id, answer_text):
    """Goes through the real submit_answer path (not process_solve directly), so these tests prove
    the rank bump actually fires on the real end-to-end solve flow, exactly like a player would
    trigger it — not just that process_solve's internals are correct in isolation."""
    from app.sessions import service as sessions_service

    response = await sessions_service.submit_answer(db, session, user_id, answer_text)
    assert response.is_correct is True and response.session_status == "SOLVED"
    return response
