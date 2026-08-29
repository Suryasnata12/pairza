"""
The matchmaking engine. This is the module the spec calls out hardest:

  "Two randomly matched users must always receive complementary clues
   belonging to the same mystery." (section 42)

and the full invariant list in section 3 — no manual selection, no repeat
strangers, no repeat mysteries, blocked/reported users excluded, backend
fully authoritative. Every rule below maps to one bullet in that list.
"""
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

from redis.asyncio import Redis
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.exceptions import ConflictError
from app.common.mixins import utcnow
from app.common.redis_client import RedisKeys
from app.config.settings import get_settings
from app.matchmaking.models import Match, MatchHistory
from app.moderation.models import Block
from app.mysteries.service import pick_random_mystery_for_pair, recent_mystery_ids_for_user
from app.sessions.models import MysterySession
from app.users.models import Profile, User

settings = get_settings()

LOCK_TOKEN_TTL_SECONDS = 10
POOL_SCAN_LIMIT = 200


async def _acquire_lock(redis: Redis) -> bool:
    return bool(await redis.set(RedisKeys.MATCHMAKING_LOCK, "1", nx=True, ex=LOCK_TOKEN_TTL_SECONDS))


async def _release_lock(redis: Redis) -> None:
    await redis.delete(RedisKeys.MATCHMAKING_LOCK)


async def _has_active_session(db: AsyncSession, user_id: uuid.UUID) -> MysterySession | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status.in_(["WAITING", "ACTIVE"]),
            MysterySession.expires_at > now,
            or_(MysterySession.player_a_id == user_id, MysterySession.player_b_id == user_id),
        )
    )
    return result.scalars().first()


async def _is_blocked_pair(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    result = await db.execute(
        select(Block).where(
            or_(
                (Block.blocker_id == user_a) & (Block.blocked_id == user_b),
                (Block.blocker_id == user_b) & (Block.blocked_id == user_a),
            )
        )
    )
    return result.scalars().first() is not None


async def _recently_matched(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    cutoff = utcnow() - timedelta(days=settings.MATCH_COOLDOWN_DAYS)
    result = await db.execute(
        select(MatchHistory).where(
            MatchHistory.user_id == user_a,
            MatchHistory.matched_with_user_id == user_b,
            MatchHistory.created_at >= cutoff,
        )
    )
    return result.scalars().first() is not None


async def _is_eligible_candidate(db: AsyncSession, candidate_id: uuid.UUID) -> bool:
    result = await db.execute(select(User).where(User.id == candidate_id))
    candidate = result.scalar_one_or_none()
    if candidate is None:
        return False
    return candidate.is_active and not candidate.is_banned and not candidate.is_suspended


async def join_matchmaking(db: AsyncSession, redis: Redis, user: User) -> dict:
    # Idempotent: calling /matchmaking/join twice in a row just returns
    # whatever you've already got instead of creating a second session.
    existing = await _has_active_session(db, user.id)
    if existing:
        return {"status": "matched", "session": existing}

    if user.is_suspended or user.is_banned:
        raise ConflictError("This account can't join matchmaking right now.", code="account_restricted")

    # Critical section: pop-a-partner-and-create-session must be atomic
    # across concurrent requests, or two different callers could both grab
    # the same waiting user and create two sessions for them.
    got_lock = await _acquire_lock(redis)
    if not got_lock:
        # Someone else is mid-pairing — the caller just joins the pool and
        # will pick up their match on the next status poll.
        await redis.zadd(RedisKeys.MATCHMAKING_POOL, {str(user.id): time.time()})
        return {"status": "waiting"}

    try:
        pool = await redis.zrange(RedisKeys.MATCHMAKING_POOL, 0, POOL_SCAN_LIMIT - 1)
        partner_id: uuid.UUID | None = None

        for candidate_str in pool:
            candidate_id = uuid.UUID(candidate_str)
            if candidate_id == user.id:
                continue
            if not await _is_eligible_candidate(db, candidate_id):
                await redis.zrem(RedisKeys.MATCHMAKING_POOL, candidate_str)
                continue
            if await _is_blocked_pair(db, user.id, candidate_id):
                continue
            if await _recently_matched(db, user.id, candidate_id):
                continue
            partner_id = candidate_id
            break

        if partner_id is None:
            await redis.zadd(RedisKeys.MATCHMAKING_POOL, {str(user.id): time.time()})
            return {"status": "waiting"}

        # Found a partner — remove both from the pool before anything else
        # so no third caller can grab either of them mid-creation.
        await redis.zrem(RedisKeys.MATCHMAKING_POOL, str(partner_id))
        await redis.zrem(RedisKeys.MATCHMAKING_POOL, str(user.id))

        cooldown_cutoff = utcnow() - timedelta(days=settings.MYSTERY_COOLDOWN_DAYS)
        recent_a = await recent_mystery_ids_for_user(db, user.id, cooldown_cutoff)
        recent_b = await recent_mystery_ids_for_user(db, partner_id, cooldown_cutoff)
        mystery = await pick_random_mystery_for_pair(db, user.id, partner_id, recent_a | recent_b)

        if mystery is None:
            # No eligible mystery for this pair right now (e.g. a very
            # small seed set) — put both back and report waiting rather
            # than creating a broken session.
            await redis.zadd(RedisKeys.MATCHMAKING_POOL, {str(user.id): time.time()})
            await redis.zadd(RedisKeys.MATCHMAKING_POOL, {str(partner_id): time.time()})
            return {"status": "waiting"}

        # Randomize which real user gets the "player_a" clue role so role
        # assignment carries no meaning beyond "which half of the pair."
        user_ids = [user.id, partner_id]
        random.shuffle(user_ids)
        player_a_id, player_b_id = user_ids

        now = utcnow()
        match = Match(user_a_id=player_a_id, user_b_id=player_b_id, mystery_id=mystery.id, created_at=now)
        db.add(match)
        await db.flush()

        session = MysterySession(
            match_id=match.id,
            mystery_id=mystery.id,
            player_a_id=player_a_id,
            player_b_id=player_b_id,
            status="ACTIVE",
            current_stage_number=1,
            started_at=now,
            expires_at=now + timedelta(hours=settings.SESSION_DURATION_HOURS),
        )
        db.add(session)

        db.add(MatchHistory(user_id=player_a_id, matched_with_user_id=player_b_id, match_id=match.id, created_at=now))
        db.add(MatchHistory(user_id=player_b_id, matched_with_user_id=player_a_id, match_id=match.id, created_at=now))

        await db.commit()
        await db.refresh(session)
        return {"status": "matched", "session": session}
    finally:
        await _release_lock(redis)


async def leave_matchmaking(redis: Redis, user: User) -> None:
    await redis.zrem(RedisKeys.MATCHMAKING_POOL, str(user.id))


async def get_status(db: AsyncSession, redis: Redis, user: User) -> dict:
    existing = await _has_active_session(db, user.id)
    if existing:
        return {"status": "matched", "session": existing}

    rank = await redis.zrank(RedisKeys.MATCHMAKING_POOL, str(user.id))
    if rank is not None:
        return {"status": "waiting", "session": None}

    return {"status": "idle", "session": None}


async def partner_profile_teaser(db: AsyncSession, session: MysterySession, viewer_id: uuid.UUID) -> Profile | None:
    """Section 11: show only country/timezone/interests/language/experience — never exact location or contact info."""
    partner_id = session.partner_id(viewer_id)
    if partner_id is None:
        return None
    result = await db.execute(select(Profile).where(Profile.user_id == partner_id))
    return result.scalar_one_or_none()
