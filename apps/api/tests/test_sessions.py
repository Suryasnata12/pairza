from datetime import timedelta

import pytest
from sqlalchemy import select

from app.common.exceptions import ConflictError
from app.common.mixins import utcnow
from app.matchmaking.models import Match
from app.mysteries.difficulty import time_limit_for_difficulty
from app.rewards.models import UserBadge
from app.sessions import service as sessions_service
from app.sessions.models import InvestigationEvidence, MysterySession, MysterySubmission, UserMysteryHistory
from app.sessions.schemas import EvidenceCreate
from tests.conftest import make_mystery, make_user


async def _create_session_directly(
    db, mystery, user_a, user_b, expires_in: timedelta | None = None, started_ago: timedelta = timedelta(0),
) -> MysterySession:
    """Bypasses matchmaking to set up a session for tests that only care about session-domain logic.

    By default the session gets exactly what matchmaking would give it: the FULL time limit for the
    mystery's difficulty, starting now. `expires_in` overrides the time remaining (negative = already
    past its deadline); `started_ago` backdates the start, which uses up that much of the time limit.
    """
    now = utcnow()
    started_at = now - started_ago
    if expires_in is not None:
        expires_at = now + expires_in
    else:
        expires_at = started_at + time_limit_for_difficulty(mystery.difficulty)
    match = Match(user_a_id=user_a.id, user_b_id=user_b.id, mystery_id=mystery.id, created_at=now)
    db.add(match)
    await db.flush()
    session = MysterySession(
        match_id=match.id, mystery_id=mystery.id, player_a_id=user_a.id, player_b_id=user_b.id,
        status="ACTIVE", current_stage_number=1, started_at=started_at, expires_at=expires_at,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def test_correct_final_answer_solves_and_awards_xp(db):
    mystery = await make_mystery(db, final_answers=["blue car", "a blue car"])
    user_a = await make_user(db, "sa1@test.com", "sa1")
    user_b = await make_user(db, "sb1@test.com", "sb1")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    response = await sessions_service.submit_answer(db, session, user_a.id, "A Blue Car!")

    assert response.is_correct is True
    assert response.session_status == "SOLVED"
    assert response.xp_awarded > 0

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == session.id))).scalar_one()
    assert refreshed.status == "SOLVED"
    assert refreshed.solved_at is not None


async def test_incorrect_answer_does_not_solve(db):
    mystery = await make_mystery(db, final_answers=["correct answer"])
    user_a = await make_user(db, "sa2@test.com", "sa2")
    user_b = await make_user(db, "sb2@test.com", "sb2")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    response = await sessions_service.submit_answer(db, session, user_a.id, "totally wrong")

    assert response.is_correct is False
    assert response.session_status == "ACTIVE"

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == session.id))).scalar_one()
    assert refreshed.status == "ACTIVE"


async def test_checkpoint_advances_stage_without_solving(db):
    mystery = await make_mystery(db, two_stage=True, final_answers=["final answer"])
    user_a = await make_user(db, "sa3@test.com", "sa3")
    user_b = await make_user(db, "sb3@test.com", "sb3")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    response = await sessions_service.submit_answer(db, session, user_a.id, "checkpoint")

    assert response.is_correct is True
    assert response.session_status == "ACTIVE"
    assert response.current_stage_number == 2

    detail = await sessions_service.build_session_detail(db, session, user_a.id)
    assert len(detail.mystery.stages) == 2
    assert detail.mystery.stages[1].your_clue is not None


async def test_stage_two_clue_hidden_until_checkpoint_passed(db):
    mystery = await make_mystery(db, two_stage=True)
    user_a = await make_user(db, "sa4@test.com", "sa4")
    user_b = await make_user(db, "sb4@test.com", "sb4")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    detail = await sessions_service.build_session_detail(db, session, user_a.id)
    # Only stage 1 should be visible before the checkpoint is solved.
    assert len(detail.mystery.stages) == 1
    assert detail.mystery.stages[0].stage_number == 1


async def test_expired_session_is_authoritatively_marked_by_backend(db):
    mystery = await make_mystery(db)
    user_a = await make_user(db, "sa5@test.com", "sa5")
    user_b = await make_user(db, "sb5@test.com", "sb5")
    # Create a session that is already past its deadline — simulates the time limit elapsing.
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in=timedelta(seconds=-1))

    checked = await sessions_service.ensure_not_expired(db, session)

    assert checked.status == "EXPIRED"

    from app.sessions.models import UserMysteryHistory
    history = (await db.execute(select(UserMysteryHistory).where(UserMysteryHistory.user_id == user_a.id))).scalars().all()
    assert len(history) == 1
    assert history[0].result == "expired"


async def test_answering_after_expiry_is_rejected_even_with_correct_text(db):
    """Backend authority: a client can't sneak a correct answer in after the clock (server-side) has run out."""
    mystery = await make_mystery(db, final_answers=["correct answer"])
    user_a = await make_user(db, "sa6@test.com", "sa6")
    user_b = await make_user(db, "sb6@test.com", "sb6")
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in=timedelta(seconds=-1))

    checked = await sessions_service.ensure_not_expired(db, session)
    assert checked.status == "EXPIRED"

    from app.common.exceptions import ConflictError
    try:
        await sessions_service.submit_answer(db, checked, user_a.id, "correct answer")
        assert False, "expected ConflictError for answering an expired session"
    except ConflictError:
        pass


async def test_evidence_is_visible_to_both_participants(db):
    mystery = await make_mystery(db)
    user_a = await make_user(db, "sa7@test.com", "sa7")
    user_b = await make_user(db, "sb7@test.com", "sb7")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    await sessions_service.add_evidence(db, session, user_a.id, EvidenceCreate(title="A clue", content="Something A found"))

    detail_a = await sessions_service.build_session_detail(db, session, user_a.id)
    detail_b = await sessions_service.build_session_detail(db, session, user_b.id)
    assert len(detail_a.evidence) == 1
    assert len(detail_b.evidence) == 1
    assert detail_a.evidence[0].content == "Something A found"


async def test_solving_awards_first_solve_badge(db):
    mystery = await make_mystery(db, final_answers=["correct answer"])
    user_a = await make_user(db, "sa8@test.com", "sa8")
    user_b = await make_user(db, "sb8@test.com", "sb8")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    from app.rewards.models import Badge
    db.add(Badge(code="FIRST_SOLVE", name="First!", description="d", icon="i", criteria_type="first_solve", criteria_value=1))
    await db.commit()

    response = await sessions_service.submit_answer(db, session, user_a.id, "correct answer")
    assert "FIRST_SOLVE" in response.new_badges

    badge_rows = (await db.execute(select(UserBadge).where(UserBadge.user_id == user_a.id))).scalars().all()
    assert len(badge_rows) == 1


# --- Difficulty-based time limits -------------------------------------------------------------

async def test_default_test_session_uses_the_difficulty_time_limit(db):
    """The helper mirrors matchmaking: end time = start + the limit for the mystery's difficulty."""
    mystery = await make_mystery(db, title="Limit Check", difficulty=4)
    user_a = await make_user(db, "tl1a@test.com", "tl1a")
    user_b = await make_user(db, "tl1b@test.com", "tl1b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    assert session.expires_at - session.started_at == timedelta(minutes=20)


async def test_session_detail_exposes_deadline_duration_and_server_clock(db):
    mystery = await make_mystery(db, title="Detail Fields", difficulty=3)
    user_a = await make_user(db, "tl2a@test.com", "tl2a")
    user_b = await make_user(db, "tl2b@test.com", "tl2b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    detail = await sessions_service.build_session_detail(db, session, user_a.id)

    assert detail.duration_seconds == 15 * 60
    assert detail.expires_at - detail.started_at == timedelta(minutes=15)
    assert detail.expiring_warning_seconds == 3 * 60  # last fifth of 15 minutes
    assert 15 * 60 - 5 <= detail.seconds_remaining <= 15 * 60
    assert detail.mystery.time_limit_seconds == 15 * 60
    # `server_time` is what lets a client with a wrong device clock still show the right countdown.
    assert abs((detail.server_time - utcnow()).total_seconds()) < 5


async def test_both_players_see_the_same_deadline_and_a_refresh_does_not_reset_it(db):
    mystery = await make_mystery(db, title="Shared Clock", difficulty=2)
    user_a = await make_user(db, "tl3a@test.com", "tl3a")
    user_b = await make_user(db, "tl3b@test.com", "tl3b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    detail_a = await sessions_service.build_session_detail(db, session, user_a.id)
    detail_b = await sessions_service.build_session_detail(db, session, user_b.id)
    refreshed_a = await sessions_service.build_session_detail(db, session, user_a.id)  # what a page reload does

    assert detail_a.expires_at == detail_b.expires_at == refreshed_a.expires_at
    assert detail_a.started_at == detail_b.started_at == refreshed_a.started_at
    assert detail_a.duration_seconds == detail_b.duration_seconds == 10 * 60
    assert abs(detail_a.seconds_remaining - detail_b.seconds_remaining) <= 1


async def test_answer_after_deadline_is_rejected_even_before_the_sweeper_notices(db):
    """The deadline has passed but the row still says ACTIVE (sweeper hasn't run, and the router's
    pre-check raced the clock). submit_answer must re-check under its own lock: a correct answer
    after time is up is never scored, and the session is settled through the normal timeout path."""
    mystery = await make_mystery(db, title="Too Late", final_answers=["correct answer"], difficulty=1)
    user_a = await make_user(db, "tl4a@test.com", "tl4a")
    user_b = await make_user(db, "tl4b@test.com", "tl4b")
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in=timedelta(seconds=-1))
    assert session.status == "ACTIVE"

    with pytest.raises(ConflictError) as exc_info:
        await sessions_service.submit_answer(db, session, user_a.id, "correct answer")
    assert exc_info.value.code == "session_expired"

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == session.id))).scalar_one()
    assert refreshed.status == "EXPIRED"
    assert refreshed.solved_at is None
    assert refreshed.ended_at is not None

    submissions = (await db.execute(select(MysterySubmission).where(MysterySubmission.session_id == session.id))).scalars().all()
    assert submissions == []  # the late answer was never even recorded

    history = (await db.execute(select(UserMysteryHistory).where(UserMysteryHistory.session_id == session.id))).scalars().all()
    assert sorted(h.result for h in history) == ["expired", "expired"]  # existing timeout handling, once per player


async def test_evidence_after_deadline_is_rejected(db):
    mystery = await make_mystery(db, title="Late Evidence", difficulty=1)
    user_a = await make_user(db, "tl5a@test.com", "tl5a")
    user_b = await make_user(db, "tl5b@test.com", "tl5b")
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in=timedelta(seconds=-1))

    with pytest.raises(ConflictError) as exc_info:
        await sessions_service.add_evidence(db, session, user_a.id, EvidenceCreate(title="Too late", content="x"))
    assert exc_info.value.code == "session_expired"

    rows = (await db.execute(select(InvestigationEvidence).where(InvestigationEvidence.session_id == session.id))).scalars().all()
    assert rows == []


async def test_is_open_for_play_reflects_the_deadline(db):
    """The check the WebSocket chat uses for every message."""
    mystery = await make_mystery(db, title="Open For Play", difficulty=2)
    user_a = await make_user(db, "tl6a@test.com", "tl6a")
    user_b = await make_user(db, "tl6b@test.com", "tl6b")
    user_c = await make_user(db, "tl6c@test.com", "tl6c")
    user_d = await make_user(db, "tl6d@test.com", "tl6d")
    live = await _create_session_directly(db, mystery, user_a, user_b)
    dead = await _create_session_directly(db, mystery, user_c, user_d, expires_in=timedelta(seconds=-1))

    assert await sessions_service.is_open_for_play(db, live.id) is True
    assert await sessions_service.is_open_for_play(db, dead.id) is False

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == dead.id))).scalar_one()
    assert refreshed.status == "EXPIRED"  # checking also settles it via the normal lifecycle


async def test_is_open_for_play_is_false_for_unknown_session(db):
    import uuid
    assert await sessions_service.is_open_for_play(db, uuid.uuid4()) is False


# --- "Expiring soon" warning scales with each session's own time limit --------------------------

async def test_a_fresh_short_session_is_not_warned_immediately(db):
    """Regression guard: the old fixed 60-minute warning window would have flagged every
    5-minute session as 'expiring' the instant it started."""
    mystery = await make_mystery(db, title="Fresh Short", difficulty=1)
    user_a = await make_user(db, "tl7a@test.com", "tl7a")
    user_b = await make_user(db, "tl7b@test.com", "tl7b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    assert await sessions_service.sweep_expiring_warnings(db) == 0
    await db.refresh(session)
    assert session.expiring_notice_sent is False


async def test_warning_fires_in_the_last_fifth_of_the_time_limit(db):
    mystery = await make_mystery(db, title="Nearly Out", difficulty=1)  # 5 min -> warns inside the final 60s
    user_a = await make_user(db, "tl8a@test.com", "tl8a")
    user_b = await make_user(db, "tl8b@test.com", "tl8b")
    session = await _create_session_directly(db, mystery, user_a, user_b, started_ago=timedelta(minutes=4, seconds=10))

    assert await sessions_service.sweep_expiring_warnings(db) == 1
    await db.refresh(session)
    assert session.expiring_notice_sent is True
    assert await sessions_service.sweep_expiring_warnings(db) == 0  # one-time only


async def test_warning_window_scales_with_the_time_limit(db):
    mystery = await make_mystery(db, title="Long One", difficulty=5)  # 30 min -> warns inside the final 6 min
    user_a = await make_user(db, "tl9a@test.com", "tl9a")
    user_b = await make_user(db, "tl9b@test.com", "tl9b")
    user_c = await make_user(db, "tl9c@test.com", "tl9c")
    user_d = await make_user(db, "tl9d@test.com", "tl9d")
    far = await _create_session_directly(db, mystery, user_a, user_b, started_ago=timedelta(minutes=10))   # 20 min left
    near = await _create_session_directly(db, mystery, user_c, user_d, started_ago=timedelta(minutes=25))  # 5 min left

    # A 5-minute mystery with 4 minutes left is INSIDE the widest window any tier has (6 min) but
    # OUTSIDE its own (1 min) — the per-session check must leave it alone.
    short_mystery = await make_mystery(db, title="Short One", difficulty=1)
    user_e = await make_user(db, "tl9e@test.com", "tl9e")
    user_f = await make_user(db, "tl9f@test.com", "tl9f")
    short_early = await _create_session_directly(db, short_mystery, user_e, user_f, started_ago=timedelta(minutes=1))  # 4 min left

    assert await sessions_service.sweep_expiring_warnings(db) == 1
    await db.refresh(far)
    await db.refresh(near)
    await db.refresh(short_early)
    assert far.expiring_notice_sent is False
    assert near.expiring_notice_sent is True
    assert short_early.expiring_notice_sent is False
