"""
Everything that happens the instant a session becomes terminal (SOLVED,
FAILED, or EXPIRED) lives here: XP math, streaks, badge unlocks, the
Memory Vault entry, and the history row that keeps matchmaking/mystery
selection from repeating itself. sessions/service.py calls into this
exactly once per terminal transition — see the `with_for_update` guard
there that keeps this from double-firing.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.mixins import utcnow
from app.mysteries.models import Mystery
from app.rewards.models import Badge, Reward, UserBadge
from app.sessions.models import Memory, MysterySession, UserMysteryHistory
from app.users.models import Profile

BASE_SOLVE_XP = 100


def calculate_speed_bonus(solve_seconds: float) -> int:
    if solve_seconds < 300:
        return 100
    if solve_seconds < 900:
        return 60
    if solve_seconds < 3600:
        return 30
    if solve_seconds < 14400:
        return 10
    return 0


def calculate_streak_bonus(current_streak: int) -> int:
    return min(current_streak * 5, 100)


# criteria_type -> a function(profile) -> bool "does this profile now qualify"
def _badge_qualifies(profile: Profile, badge: Badge) -> bool:
    if badge.criteria_type == "first_solve":
        return profile.solved_count >= 1
    if badge.criteria_type == "solve_count":
        return profile.solved_count >= badge.criteria_value
    if badge.criteria_type == "streak":
        return profile.current_streak >= badge.criteria_value
    if badge.criteria_type == "countries":
        return len(profile.countries_encountered) >= badge.criteria_value
    if badge.criteria_type == "categories":
        return len(profile.categories_completed) >= badge.criteria_value
    if badge.criteria_type == "speed_solver":
        # criteria_value is a threshold in seconds; checked by the caller
        # against the specific solve, since it's per-solve not cumulative.
        return False
    return False


async def check_and_award_badges(
    db: AsyncSession, profile: Profile, just_solved_in_seconds: float | None = None
) -> list[str]:
    all_badges = (await db.execute(select(Badge))).scalars().all()
    already_earned = set(
        (await db.execute(select(UserBadge.badge_id).where(UserBadge.user_id == profile.user_id))).scalars().all()
    )

    newly_awarded: list[str] = []
    for badge in all_badges:
        if badge.id in already_earned:
            continue

        qualifies = _badge_qualifies(profile, badge)
        if badge.criteria_type == "speed_solver" and just_solved_in_seconds is not None:
            qualifies = just_solved_in_seconds <= badge.criteria_value

        if qualifies:
            db.add(UserBadge(user_id=profile.user_id, badge_id=badge.id, earned_at=utcnow()))
            newly_awarded.append(badge.code)

    return newly_awarded


def _update_streak(profile: Profile, today: date) -> None:
    if profile.last_active_date is None:
        profile.current_streak = 1
    else:
        last_date = profile.last_active_date.date() if hasattr(profile.last_active_date, "date") else profile.last_active_date
        if last_date == today:
            pass  # already played today — streak unchanged
        elif last_date == today - timedelta(days=1):
            profile.current_streak += 1
        else:
            profile.current_streak = 1
    profile.longest_streak = max(profile.longest_streak, profile.current_streak)
    profile.last_active_date = today


async def process_solve(db: AsyncSession, session: MysterySession, mystery: Mystery) -> dict[uuid.UUID, dict]:
    solve_seconds = (session.solved_at - session.started_at).total_seconds()
    today = utcnow().date()

    profiles: dict[uuid.UUID, Profile] = {}
    for uid in (session.player_a_id, session.player_b_id):
        result = await db.execute(select(Profile).where(Profile.user_id == uid))
        profiles[uid] = result.scalar_one()

    results: dict[uuid.UUID, dict] = {}

    for uid, profile in profiles.items():
        partner_id = session.partner_id(uid)
        partner_profile = profiles[partner_id]

        _update_streak(profile, today)
        speed_bonus = calculate_speed_bonus(solve_seconds)
        streak_bonus = calculate_streak_bonus(profile.current_streak)
        xp_gain = BASE_SOLVE_XP + speed_bonus + streak_bonus

        profile.xp += xp_gain
        profile.mystery_count += 1
        profile.solved_count += 1

        prior_total = (profile.average_solve_seconds or 0) * (profile.solved_count - 1)
        profile.average_solve_seconds = (prior_total + solve_seconds) / profile.solved_count

        if partner_profile.country_code not in profile.countries_encountered:
            profile.countries_encountered = [*profile.countries_encountered, partner_profile.country_code]
        if mystery.category not in profile.categories_completed:
            profile.categories_completed = [*profile.categories_completed, mystery.category]

        db.add(Reward(user_id=uid, session_id=session.id, type="xp", amount=BASE_SOLVE_XP + speed_bonus, reason="mystery_solved", created_at=utcnow()))
        if streak_bonus > 0:
            db.add(Reward(user_id=uid, session_id=session.id, type="xp", amount=streak_bonus, reason="streak_bonus", created_at=utcnow()))

        db.add(UserMysteryHistory(
            user_id=uid, mystery_id=mystery.id, session_id=session.id, category=mystery.category,
            result="solved", solve_seconds=solve_seconds, created_at=utcnow(),
        ))
        db.add(Memory(
            user_id=uid, session_id=session.id, mystery_title=mystery.title,
            partner_country_code=partner_profile.country_code, solved=True, solve_seconds=solve_seconds,
            day_number=profile.mystery_count, created_at=utcnow(),
        ))

        new_badges = await check_and_award_badges(db, profile, just_solved_in_seconds=solve_seconds)
        results[uid] = {"xp_awarded": xp_gain, "new_badge_codes": new_badges}

    await db.commit()
    return results


async def process_non_solve(db: AsyncSession, session: MysterySession, mystery: Mystery, result: str) -> None:
    """result is 'expired' or 'failed'. No XP, and the streak breaks."""
    profiles: dict[uuid.UUID, Profile] = {}
    for uid in (session.player_a_id, session.player_b_id):
        r = await db.execute(select(Profile).where(Profile.user_id == uid))
        profiles[uid] = r.scalar_one()

    for uid, profile in profiles.items():
        partner_id = session.partner_id(uid)
        partner_profile = profiles[partner_id]

        profile.mystery_count += 1
        profile.current_streak = 0

        db.add(UserMysteryHistory(
            user_id=uid, mystery_id=mystery.id, session_id=session.id, category=mystery.category,
            result=result, solve_seconds=None, created_at=utcnow(),
        ))
        db.add(Memory(
            user_id=uid, session_id=session.id, mystery_title=mystery.title,
            partner_country_code=partner_profile.country_code, solved=False, solve_seconds=None,
            day_number=profile.mystery_count, created_at=utcnow(),
        ))

    await db.commit()
