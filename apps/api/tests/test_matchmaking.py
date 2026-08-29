import uuid

import pytest
from redis.asyncio import from_url

from app.matchmaking import service as matchmaking_service
from app.matchmaking.models import MatchHistory
from app.moderation.models import Block
from app.sessions.models import MysterySession
from tests.conftest import make_mystery, make_user


@pytest.fixture
async def redis():
    r = from_url("redis://localhost:6379/1", decode_responses=True)
    yield r
    await r.aclose()


async def test_two_matched_users_get_same_mystery_but_different_clues(db, redis):
    """The single most important invariant in the entire product."""
    await make_mystery(db, title="M1")
    user_a = await make_user(db, "a@test.com", "user_a")
    user_b = await make_user(db, "b@test.com", "user_b")

    result_a = await matchmaking_service.join_matchmaking(db, redis, user_a)
    assert result_a["status"] == "waiting"

    result_b = await matchmaking_service.join_matchmaking(db, redis, user_b)
    assert result_b["status"] == "matched"
    session = result_b["session"]

    from app.sessions.service import build_session_detail
    detail_a = await build_session_detail(db, session, user_a.id)
    detail_b = await build_session_detail(db, session, user_b.id)

    # Same session, same mystery.
    assert detail_a.id == detail_b.id == session.id
    assert detail_a.mystery.id == detail_b.mystery.id

    # But their clue text must differ — that's the entire mechanic.
    clue_a = detail_a.mystery.stages[0].your_clue.text
    clue_b = detail_b.mystery.stages[0].your_clue.text
    assert clue_a != clue_b
    assert clue_a in ("Clue for A", "Clue for B")
    assert clue_b in ("Clue for A", "Clue for B")
    assert clue_a != clue_b  # neither ever sees the other's exact clue


async def test_user_cannot_match_with_themselves(db, redis):
    await make_mystery(db)
    user_a = await make_user(db, "solo@test.com", "solo_user")

    result = await matchmaking_service.join_matchmaking(db, redis, user_a)
    assert result["status"] == "waiting"
    # Only one user in the pool — joining again should stay idempotent/waiting, never self-matched.
    result2 = await matchmaking_service.join_matchmaking(db, redis, user_a)
    assert result2["status"] == "waiting"

    sessions = (await db.execute(__import__("sqlalchemy").select(MysterySession))).scalars().all()
    assert len(sessions) == 0


async def test_blocked_users_are_never_matched(db, redis):
    await make_mystery(db)
    user_a = await make_user(db, "blocker@test.com", "blocker")
    user_b = await make_user(db, "blocked@test.com", "blockee")

    db.add(Block(blocker_id=user_a.id, blocked_id=user_b.id, created_at=__import__("app.common.mixins", fromlist=["utcnow"]).utcnow()))
    await db.commit()

    await matchmaking_service.join_matchmaking(db, redis, user_a)
    result_b = await matchmaking_service.join_matchmaking(db, redis, user_b)

    # No eligible partner (the only other candidate is blocked) -> stays waiting, no session created.
    assert result_b["status"] == "waiting"
    sessions = (await db.execute(__import__("sqlalchemy").select(MysterySession))).scalars().all()
    assert len(sessions) == 0


async def test_recently_matched_pair_is_excluded_by_cooldown(db, redis):
    await make_mystery(db, title="M1")
    await make_mystery(db, title="M2")
    user_a = await make_user(db, "a2@test.com", "user_a2")
    user_b = await make_user(db, "b2@test.com", "user_b2")

    r1 = await matchmaking_service.join_matchmaking(db, redis, user_a)
    r2 = await matchmaking_service.join_matchmaking(db, redis, user_b)
    assert r2["status"] == "matched"
    first_session_id = r2["session"].id

    # Expire that session out of the way, then try to re-match the same pair immediately.
    from sqlalchemy import select
    session_row = (await db.execute(select(MysterySession).where(MysterySession.id == first_session_id))).scalar_one()
    session_row.status = "EXPIRED"
    await db.commit()

    r3 = await matchmaking_service.join_matchmaking(db, redis, user_a)
    r4 = await matchmaking_service.join_matchmaking(db, redis, user_b)

    # They were matched within the cooldown window — must NOT pair again.
    assert r4["status"] == "waiting"

    history_count = (await db.execute(select(MatchHistory))).scalars().all()
    assert len(history_count) == 2  # only the one original match's two directional rows


async def test_join_is_idempotent_when_already_matched(db, redis):
    await make_mystery(db)
    user_a = await make_user(db, "idem_a@test.com", "idem_a")
    user_b = await make_user(db, "idem_b@test.com", "idem_b")

    await matchmaking_service.join_matchmaking(db, redis, user_a)
    result_b1 = await matchmaking_service.join_matchmaking(db, redis, user_b)
    session_id_1 = result_b1["session"].id

    # Calling join again while already matched must return the SAME session, not create a second one.
    result_b2 = await matchmaking_service.join_matchmaking(db, redis, user_b)
    assert result_b2["session"].id == session_id_1

    from sqlalchemy import select
    all_sessions = (await db.execute(select(MysterySession))).scalars().all()
    assert len(all_sessions) == 1
