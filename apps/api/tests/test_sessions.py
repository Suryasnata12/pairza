from datetime import timedelta

from sqlalchemy import select

from app.common.mixins import utcnow
from app.matchmaking.models import Match
from app.rewards.models import UserBadge
from app.sessions import service as sessions_service
from app.sessions.models import MysterySession
from app.sessions.schemas import EvidenceCreate
from tests.conftest import make_mystery, make_user


async def _create_session_directly(db, mystery, user_a, user_b, expires_in_hours=24) -> MysterySession:
    """Bypasses matchmaking to set up a session for tests that only care about session-domain logic."""
    now = utcnow()
    match = Match(user_a_id=user_a.id, user_b_id=user_b.id, mystery_id=mystery.id, created_at=now)
    db.add(match)
    await db.flush()
    session = MysterySession(
        match_id=match.id, mystery_id=mystery.id, player_a_id=user_a.id, player_b_id=user_b.id,
        status="ACTIVE", current_stage_number=1, started_at=now,
        expires_at=now + timedelta(hours=expires_in_hours),
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
    # Create a session that is already in the past — simulates the 24h window elapsing.
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in_hours=-1)

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
    session = await _create_session_directly(db, mystery, user_a, user_b, expires_in_hours=-1)

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
