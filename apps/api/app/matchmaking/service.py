"""
The matchmaking engine.

Two randomly matched users must receive complementary clues belonging
to the same mystery. Redis stores the transient queue and coordinates
match attempts; PostgreSQL remains authoritative for sessions.
"""

import random
import secrets
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
from app.mysteries.difficulty import session_end_time
from app.mysteries.progression import DEFAULT_DIFFICULTY_RANK
from app.mysteries.service import (
    pick_random_mystery_for_pair,
    recent_mystery_ids_for_user,
)
from app.sessions.models import MysterySession
from app.users.models import Profile, User

settings = get_settings()

# Give the matching operation a longer window than the previous 10 seconds.
LOCK_TOKEN_TTL_SECONDS = 60
POOL_SCAN_LIMIT = 200

# A process may only release a lock if it still owns that lock.
_RELEASE_LOCK_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
end
return 0
"""


async def _acquire_lock(redis: Redis) -> str | None:
    """Acquire the matchmaking lock and return its unique ownership token."""
    token = secrets.token_urlsafe(24)
    acquired = await redis.set(
        RedisKeys.MATCHMAKING_LOCK,
        token,
        nx=True,
        ex=LOCK_TOKEN_TTL_SECONDS,
    )
    return token if acquired else None


async def _release_lock(redis: Redis, token: str) -> None:
    """Release only the lock still owned by this operation."""
    await redis.eval(
        _RELEASE_LOCK_SCRIPT,
        1,
        RedisKeys.MATCHMAKING_LOCK,
        token,
    )


async def _enqueue(redis: Redis, *user_ids: uuid.UUID) -> None:
    """Queue users without resetting their original waiting timestamps."""
    if not user_ids:
        return

    await redis.zadd(
        RedisKeys.MATCHMAKING_POOL,
        {str(user_id): time.time() for user_id in user_ids},
        nx=True,
    )


async def _has_active_session(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> MysterySession | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(MysterySession).where(
            MysterySession.status.in_(["WAITING", "ACTIVE"]),
            MysterySession.expires_at > now,
            or_(
                MysterySession.player_a_id == user_id,
                MysterySession.player_b_id == user_id,
            ),
        )
    )
    return result.scalars().first()


async def _is_blocked_pair(
    db: AsyncSession,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(Block).where(
            or_(
                (Block.blocker_id == user_a)
                & (Block.blocked_id == user_b),
                (Block.blocker_id == user_b)
                & (Block.blocked_id == user_a),
            )
        )
    )
    return result.scalars().first() is not None


async def _recently_matched(
    db: AsyncSession,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> bool:
    cutoff = utcnow() - timedelta(days=settings.MATCH_COOLDOWN_DAYS)
    result = await db.execute(
        select(MatchHistory).where(
            MatchHistory.user_id == user_a,
            MatchHistory.matched_with_user_id == user_b,
            MatchHistory.created_at >= cutoff,
        )
    )
    return result.scalars().first() is not None


async def _difficulty_rank(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> int:
    """Return a player's rank, falling back to the default when missing."""
    result = await db.execute(
        select(Profile.difficulty_rank).where(Profile.user_id == user_id)
    )
    rank = result.scalar_one_or_none()
    return rank if rank is not None else DEFAULT_DIFFICULTY_RANK


async def _is_eligible_candidate(
    db: AsyncSession,
    candidate_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(User).where(User.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()

    if candidate is None:
        return False

    return (
        candidate.is_active
        and not candidate.is_banned
        and not candidate.is_suspended
    )


async def join_matchmaking(
    db: AsyncSession,
    redis: Redis,
    user: User,
) -> dict:
    # Idempotent: don't create another session for a user already matched.
    existing = await _has_active_session(db, user.id)
    if existing:
        await redis.zrem(RedisKeys.MATCHMAKING_POOL, str(user.id))
        return {"status": "matched", "session": existing}

    if user.is_suspended or user.is_banned:
        raise ConflictError(
            "This account can't join matchmaking right now.",
            code="account_restricted",
        )

    if settings.EMAIL_VERIFICATION_REQUIRED and not user.is_verified:
        raise ConflictError(
            "Verify your email before joining matchmaking.",
            code="email_not_verified",
        )

    # A lock loser still joins the queue. The next status poll will retry.
    lock_token = await _acquire_lock(redis)
    if lock_token is None:
        await _enqueue(redis, user.id)
        return {"status": "waiting"}

    try:
        # Recheck after acquiring the lock. A concurrent request may have
        # matched this user after the first active-session check.
        existing = await _has_active_session(db, user.id)
        if existing:
            await redis.zrem(
                RedisKeys.MATCHMAKING_POOL,
                str(user.id),
            )
            return {"status": "matched", "session": existing}

        pool = await redis.zrange(
            RedisKeys.MATCHMAKING_POOL,
            0,
            POOL_SCAN_LIMIT - 1,
        )
        partner_id: uuid.UUID | None = None

        for candidate_str in pool:
            try:
                candidate_id = uuid.UUID(candidate_str)
            except (ValueError, TypeError, AttributeError):
                # Remove malformed entries instead of allowing them to
                # interrupt future matchmaking attempts.
                await redis.zrem(
                    RedisKeys.MATCHMAKING_POOL,
                    candidate_str,
                )
                continue

            if candidate_id == user.id:
                continue

            if not await _is_eligible_candidate(db, candidate_id):
                await redis.zrem(
                    RedisKeys.MATCHMAKING_POOL,
                    candidate_str,
                )
                continue

            # A candidate may have been matched by another completed
            # operation while an old queue entry remained.
            if await _has_active_session(db, candidate_id):
                await redis.zrem(
                    RedisKeys.MATCHMAKING_POOL,
                    candidate_str,
                )
                continue

            if await _is_blocked_pair(db, user.id, candidate_id):
                continue

            if await _recently_matched(db, user.id, candidate_id):
                continue

            partner_id = candidate_id
            break

        if partner_id is None:
            await _enqueue(redis, user.id)
            return {"status": "waiting"}

        # Keep both users queued until the DB transaction commits.
        # This lets status polling see "waiting" during session creation,
        # instead of seeing "idle" while the users are temporarily absent
        # from the queue but the session has not yet committed.

        cooldown_cutoff = utcnow() - timedelta(
            days=settings.MYSTERY_COOLDOWN_DAYS
        )
        recent_a = await recent_mystery_ids_for_user(
            db, user.id, cooldown_cutoff
        )
        recent_b = await recent_mystery_ids_for_user(
            db, partner_id, cooldown_cutoff
        )

        rank_a = await _difficulty_rank(db, user.id)
        rank_b = await _difficulty_rank(db, partner_id)

        mystery = await pick_random_mystery_for_pair(
            db,
            user.id,
            partner_id,
            recent_a | recent_b,
            rank_a,
            rank_b,
        )

        if mystery is None:
            # No suitable published mystery: retain both users in the
            # queue so a later retry can try again.
            await _enqueue(redis, user.id, partner_id)
            return {"status": "waiting"}

        # Randomize which user receives each complementary clue role.
        user_ids = [user.id, partner_id]
        random.shuffle(user_ids)
        player_a_id, player_b_id = user_ids

        now = utcnow()
        match = Match(
            user_a_id=player_a_id,
            user_b_id=player_b_id,
            mystery_id=mystery.id,
            created_at=now,
        )
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
            expires_at=session_end_time(now, mystery.difficulty),
        )
        db.add(session)

        db.add(
            MatchHistory(
                user_id=player_a_id,
                matched_with_user_id=player_b_id,
                match_id=match.id,
                created_at=now,
            )
        )
        db.add(
            MatchHistory(
                user_id=player_b_id,
                matched_with_user_id=player_a_id,
                match_id=match.id,
                created_at=now,
            )
        )

        await db.commit()
        await db.refresh(session)

        # Remove queue entries only after the session is persisted.
        await redis.zrem(
            RedisKeys.MATCHMAKING_POOL,
            str(player_a_id),
            str(player_b_id),
        )

        return {"status": "matched", "session": session}

    finally:
        # A lock that expired and was acquired by another request will
        # not be deleted by this operation's stale token.
        await _release_lock(redis, lock_token)


async def leave_matchmaking(
    redis: Redis,
    user: User,
) -> None:
    await redis.zrem(
        RedisKeys.MATCHMAKING_POOL,
        str(user.id),
    )


async def get_status(
    db: AsyncSession,
    redis: Redis,
    user: User,
) -> dict:
    existing = await _has_active_session(db, user.id)
    if existing:
        await redis.zrem(
            RedisKeys.MATCHMAKING_POOL,
            str(user.id),
        )
        return {"status": "matched", "session": existing}

    rank = await redis.zrank(
        RedisKeys.MATCHMAKING_POOL,
        str(user.id),
    )

    if rank is not None:
        # Critical retry: polling is not passive. A queued player tries
        # matchmaking again, repairing the simultaneous-join race where
        # both requests saw an empty queue while the other was joining.
        return await join_matchmaking(db, redis, user)

    return {"status": "idle", "session": None}


async def partner_profile_teaser(
    db: AsyncSession,
    session: MysterySession,
    viewer_id: uuid.UUID,
) -> Profile | None:
    """Expose only the partner's permitted profile details."""
    partner_id = session.partner_id(viewer_id)
    if partner_id is None:
        return None

    result = await db.execute(
        select(Profile).where(Profile.user_id == partner_id)
    )
    return result.scalar_one_or_none()