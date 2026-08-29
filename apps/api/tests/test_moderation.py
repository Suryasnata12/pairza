from sqlalchemy import select

from app.matchmaking import service as matchmaking_service
from app.moderation import service as moderation_service
from app.sessions.models import MysterySession
from tests.conftest import make_mystery, make_user
from tests.test_sessions import _create_session_directly


async def test_blocking_partner_immediately_ends_active_session_as_failed(db):
    """This is the safety-critical one: nobody should be stuck finishing a
    mystery with someone they just blocked."""
    mystery = await make_mystery(db)
    user_a = await make_user(db, "block_a@test.com", "block_a")
    user_b = await make_user(db, "block_b@test.com", "block_b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    assert session.status == "ACTIVE"

    await moderation_service.block_user(db, blocker_id=user_b.id, blocked_id=user_a.id)

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == session.id))).scalar_one()
    assert refreshed.status == "FAILED"

    from app.sessions.models import UserMysteryHistory
    history = (await db.execute(select(UserMysteryHistory).where(UserMysteryHistory.session_id == session.id))).scalars().all()
    assert len(history) == 2  # both participants get a history row
    assert all(h.result == "failed" for h in history)


async def test_blocking_with_no_active_session_just_blocks(db):
    user_a = await make_user(db, "noblock_a@test.com", "noblock_a")
    user_b = await make_user(db, "noblock_b@test.com", "noblock_b")

    block = await moderation_service.block_user(db, blocker_id=user_a.id, blocked_id=user_b.id)
    assert block.blocked_id == user_b.id

    blocks = await moderation_service.list_blocks(db, user_a.id)
    assert len(blocks) == 1


async def test_cannot_block_self(db):
    user_a = await make_user(db, "selfblock@test.com", "selfblock")
    from app.common.exceptions import ConflictError
    try:
        await moderation_service.block_user(db, blocker_id=user_a.id, blocked_id=user_a.id)
        assert False, "expected ConflictError"
    except ConflictError:
        pass


async def test_blocked_pair_permanently_excluded_from_future_matchmaking(db):
    """Unlike the cooldown (time-limited), a block should never expire."""
    await make_mystery(db)
    user_a = await make_user(db, "permblock_a@test.com", "permblock_a")
    user_b = await make_user(db, "permblock_b@test.com", "permblock_b")

    await moderation_service.block_user(db, blocker_id=user_a.id, blocked_id=user_b.id)

    from redis.asyncio import from_url
    redis = from_url("redis://localhost:6379/1", decode_responses=True)
    try:
        await matchmaking_service.join_matchmaking(db, redis, user_a)
        result = await matchmaking_service.join_matchmaking(db, redis, user_b)
        assert result["status"] == "waiting"  # never paired despite being the only two users

        sessions = (await db.execute(select(MysterySession))).scalars().all()
        assert len(sessions) == 0
    finally:
        await redis.aclose()


async def test_unblock_removes_the_block(db):
    user_a = await make_user(db, "unblock_a@test.com", "unblock_a")
    user_b = await make_user(db, "unblock_b@test.com", "unblock_b")

    await moderation_service.block_user(db, blocker_id=user_a.id, blocked_id=user_b.id)
    assert len(await moderation_service.list_blocks(db, user_a.id)) == 1

    await moderation_service.unblock_user(db, blocker_id=user_a.id, blocked_id=user_b.id)
    assert len(await moderation_service.list_blocks(db, user_a.id)) == 0


async def test_report_does_not_end_the_session(db):
    """Reporting alone (without blocking) lets the session continue — an
    admin reviews it, but we don't force-end investigations on a single
    unverified report."""
    mystery = await make_mystery(db)
    user_a = await make_user(db, "report_a@test.com", "report_a")
    user_b = await make_user(db, "report_b@test.com", "report_b")
    session = await _create_session_directly(db, mystery, user_a, user_b)

    report = await moderation_service.create_report(
        db, reporter_id=user_a.id, reported_user_id=user_b.id, session_id=session.id,
        reason="harassment", details="Was rude in chat.",
    )
    assert report.status == "open"

    refreshed = (await db.execute(select(MysterySession).where(MysterySession.id == session.id))).scalar_one()
    assert refreshed.status == "ACTIVE"
