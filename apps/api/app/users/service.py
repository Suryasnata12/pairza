import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.rewards.models import UserBadge
from app.users.models import Profile
from app.users.schemas import ProfileResponse


async def build_profile_response(db: AsyncSession, profile: Profile) -> ProfileResponse:
    badge_count_result = await db.execute(
        select(func.count()).select_from(UserBadge).where(UserBadge.user_id == profile.user_id)
    )
    badge_count = badge_count_result.scalar_one()

    return ProfileResponse(
        user_id=profile.user_id,
        username=profile.username,
        avatar_url=profile.avatar_url,
        country_code=profile.country_code,
        xp=profile.xp,
        mystery_count=profile.mystery_count,
        solved_count=profile.solved_count,
        solve_rate=profile.solve_rate,
        current_streak=profile.current_streak,
        longest_streak=profile.longest_streak,
        countries_encountered=profile.countries_encountered,
        categories_completed=profile.categories_completed,
        average_solve_seconds=profile.average_solve_seconds,
        badge_count=badge_count,
    )


async def get_profile_by_user_id(db: AsyncSession, user_id: uuid.UUID) -> Profile | None:
    result = await db.execute(select(Profile).where(Profile.user_id == user_id))
    return result.scalar_one_or_none()
