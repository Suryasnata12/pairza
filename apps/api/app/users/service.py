import uuid
from datetime import timedelta
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.mixins import utcnow
from app.rewards.models import UserBadge
from app.users.models import Profile, UserDailyActivity, UserPreferences
from app.users.schemas import ProfileResponse
from datetime import timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


async def build_profile_response(db: AsyncSession, profile: Profile) -> ProfileResponse:
    badge_count_result = await db.execute(
        select(func.count()).select_from(UserBadge).where(UserBadge.user_id == profile.user_id)
    )
    badge_count = badge_count_result.scalar_one()
    pref_result = await db.execute(
        select(UserPreferences.timezone_region).where(
            UserPreferences.user_id == profile.user_id
        )
    )
    timezone_name = pref_result.scalar_one_or_none() or "UTC"
    try:
        user_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        user_timezone = timezone.utc
    today = utcnow().astimezone(user_timezone).date()
    last_active = profile.last_active_date
    last_active_day = (
        last_active.date()
        if hasattr(last_active, "date")
        else last_active
    )
    current_streak = profile.current_streak
    if (last_active_day is None or last_active_day < today - timedelta(days=1)):
        current_streak = 0

    return ProfileResponse(
        user_id=profile.user_id,
        username=profile.username,
        avatar_url=profile.avatar_url,
        country_code=profile.country_code,
        xp=profile.xp,
        mystery_count=profile.mystery_count,
        solved_count=profile.solved_count,
        solve_rate=profile.solve_rate,
        current_streak=current_streak,
        longest_streak=profile.longest_streak,
        countries_encountered=profile.countries_encountered,
        categories_completed=profile.categories_completed,
        average_solve_seconds=profile.average_solve_seconds,
        badge_count=badge_count,
    )


async def get_profile_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()


async def record_daily_activity(user_id: uuid.UUID) -> None:
    """
    Runs as a FastAPI background task (see common/deps.py::get_current_user)
    — after the response has already gone out, on its own fresh DB session.
    The request-scoped session it would otherwise share is typically closed
    by the time a background task actually executes, so reusing it here
    would risk an "operation on a closed session" error.

    The INSERT ... ON CONFLICT DO NOTHING makes calling this many times for
    the same user on the same day (every poll, every page load) a cheap,
    safe no-op rather than a pile of duplicate rows.
    """
    from app.common.database import AsyncSessionLocal

    today = utcnow().date()
    async with AsyncSessionLocal() as db:
        stmt = pg_insert(UserDailyActivity).values(user_id=user_id, activity_date=today)
        stmt = stmt.on_conflict_do_nothing(index_elements=["user_id", "activity_date"])
        await db.execute(stmt)
        await db.commit()
