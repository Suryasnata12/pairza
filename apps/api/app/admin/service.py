import uuid
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.common.exceptions import NotFoundError
from app.common.mixins import utcnow
from app.matchmaking.models import MatchHistory
from app.moderation.models import Report
from app.mysteries.models import Mystery, MysteryClue, MysteryStage
from app.mysteries.schemas import MysteryCreate, MysteryUpdate
from app.sessions.models import MysterySession, UserMysteryHistory
from app.users.models import Profile, User, UserDailyActivity


async def list_users(db: AsyncSession, search: str | None, limit: int, offset: int) -> list[dict]:
    query = select(User, Profile).join(Profile, Profile.user_id == User.id)
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.email.ilike(like), Profile.username.ilike(like)))
    query = query.order_by(User.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(query)).all()
    return [{"user": u, "profile": p} for u, p in rows]


async def _get_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("That user doesn't exist.")
    return user


async def suspend_user(db: AsyncSession, user_id: uuid.UUID, reason: str) -> User:
    user = await _get_user(db, user_id)
    user.is_suspended = True
    user.suspension_reason = reason
    await db.commit()
    return user


async def unsuspend_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    user = await _get_user(db, user_id)
    user.is_suspended = False
    user.suspension_reason = None
    await db.commit()
    return user


async def ban_user(db: AsyncSession, user_id: uuid.UUID, reason: str) -> User:
    user = await _get_user(db, user_id)
    user.is_banned = True
    user.is_active = False
    user.suspension_reason = reason
    await db.commit()
    return user


async def list_reports(db: AsyncSession, status: str | None) -> list[Report]:
    query = select(Report).order_by(Report.created_at.desc())
    if status:
        query = query.where(Report.status == status)
    return list((await db.execute(query)).scalars().all())


async def review_report(db: AsyncSession, admin_id: uuid.UUID, report_id: uuid.UUID, new_status: str) -> Report:
    result = await db.execute(select(Report).where(Report.id == report_id))
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundError("That report doesn't exist.")
    report.status = new_status
    report.reviewed_by = admin_id
    report.reviewed_at = utcnow()
    await db.commit()
    return report


async def create_mystery(db: AsyncSession, admin_id: uuid.UUID, payload: MysteryCreate) -> Mystery:
    mystery = Mystery(
        title=payload.title, category=payload.category, difficulty=payload.difficulty,
        summary=payload.summary, flavor_text=payload.flavor_text,
        final_answer_patterns=payload.final_answer_patterns, is_published=False, created_by=admin_id,
    )
    db.add(mystery)
    await db.flush()

    for stage_in in payload.stages:
        stage = MysteryStage(
            mystery_id=mystery.id, stage_number=stage_in.stage_number, is_final=stage_in.is_final,
            context=stage_in.context, checkpoint_answer_patterns=stage_in.checkpoint_answer_patterns,
        )
        db.add(stage)
        await db.flush()
        for clue_in in stage_in.clues:
            db.add(MysteryClue(stage_id=stage.id, role=clue_in.role, text=clue_in.text, media_url=clue_in.media_url))

    await db.commit()
    await db.refresh(mystery)
    return mystery


async def update_mystery(db: AsyncSession, mystery_id: uuid.UUID, payload: MysteryUpdate) -> Mystery:
    result = await db.execute(select(Mystery).where(Mystery.id == mystery_id))
    mystery = result.scalar_one_or_none()
    if not mystery:
        raise NotFoundError("That mystery doesn't exist.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(mystery, field, value)
    await db.commit()
    await db.refresh(mystery)
    return mystery


async def set_publish_state(db: AsyncSession, mystery_id: uuid.UUID, is_published: bool) -> Mystery:
    result = await db.execute(select(Mystery).where(Mystery.id == mystery_id))
    mystery = result.scalar_one_or_none()
    if not mystery:
        raise NotFoundError("That mystery doesn't exist.")
    mystery.is_published = is_published
    await db.commit()
    return mystery


async def list_mysteries_admin(db: AsyncSession, category: str | None) -> list[Mystery]:
    query = select(Mystery).options(selectinload(Mystery.stages)).order_by(Mystery.created_at.desc())
    if category:
        query = query.where(Mystery.category == category)
    return list((await db.execute(query)).scalars().all())


async def list_active_sessions(db: AsyncSession) -> list[dict]:
    query = (
        select(MysterySession, Mystery.title, Mystery.category)
        .join(Mystery, Mystery.id == MysterySession.mystery_id)
        .where(MysterySession.status == "ACTIVE")
        .order_by(MysterySession.started_at.desc())
        .limit(200)
    )
    rows = (await db.execute(query)).all()
    return [{"session": s, "mystery_title": title, "category": category} for s, title, category in rows]


async def get_analytics(db: AsyncSession) -> dict:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    active_sessions = (
        await db.execute(select(func.count()).select_from(MysterySession).where(MysterySession.status == "ACTIVE"))
    ).scalar_one()

    completed_total = (
        await db.execute(select(func.count()).select_from(UserMysteryHistory))
    ).scalar_one()
    solved_total = (
        await db.execute(select(func.count()).select_from(UserMysteryHistory).where(UserMysteryHistory.result == "solved"))
    ).scalar_one()

    avg_solve = (
        await db.execute(select(func.avg(UserMysteryHistory.solve_seconds)).where(UserMysteryHistory.result == "solved"))
    ).scalar_one()

    breakdown_rows = (
        await db.execute(select(UserMysteryHistory.category, func.count()).group_by(UserMysteryHistory.category))
    ).all()

    open_reports = (
        await db.execute(select(func.count()).select_from(Report).where(Report.status == "open"))
    ).scalar_one()

    engagement = await get_engagement_metrics(db)

    return {
        "total_users": total_users,
        "active_sessions": active_sessions,
        "mysteries_completed_total": completed_total,
        "mysteries_solved_total": solved_total,
        "completion_rate": round(solved_total / completed_total, 4) if completed_total else 0.0,
        "average_solve_seconds": float(avg_solve) if avg_solve is not None else None,
        "category_breakdown": {cat: count for cat, count in breakdown_rows},
        "open_reports": open_reports,
        **engagement,
    }


# --- Engagement analytics (DAU/MAU/retention/gameplay rates) ---
#
# Everything here reads from UserDailyActivity, which is populated by a
# background task off of get_current_user (see common/deps.py) — one row
# per user per calendar day they were seen using the app at all. Nothing
# below queries live traffic directly; it's all derived from that log.

async def get_dau(db: AsyncSession, on_date=None) -> int:
    on_date = on_date or utcnow().date()
    result = await db.execute(
        select(func.count(func.distinct(UserDailyActivity.user_id))).where(
            UserDailyActivity.activity_date == on_date
        )
    )
    return result.scalar_one()


async def get_mau(db: AsyncSession, as_of=None) -> int:
    as_of = as_of or utcnow().date()
    window_start = as_of - timedelta(days=29)  # 30-day window, inclusive of today
    result = await db.execute(
        select(func.count(func.distinct(UserDailyActivity.user_id))).where(
            UserDailyActivity.activity_date >= window_start,
            UserDailyActivity.activity_date <= as_of,
        )
    )
    return result.scalar_one()


async def get_day_n_retention(db: AsyncSession, n: int, as_of=None) -> float | None:
    """
    Classic cohort Day-N retention: of the users whose very FIRST recorded
    activity was exactly `n` days before `as_of`, what fraction were active
    again on `as_of` itself (i.e., exactly `n` days later)?

    Returns None (not 0.0) when that cohort is empty — "no data yet" and
    "0% retention" are different facts, and collapsing them would make an
    early-days product look artificially like it's failing to retain anyone.
    """
    as_of = as_of or utcnow().date()
    cohort_date = as_of - timedelta(days=n)

    first_activity = (
        select(
            UserDailyActivity.user_id,
            func.min(UserDailyActivity.activity_date).label("first_date"),
        )
        .group_by(UserDailyActivity.user_id)
        .subquery()
    )

    cohort_result = await db.execute(
        select(first_activity.c.user_id).where(first_activity.c.first_date == cohort_date)
    )
    cohort_user_ids = list(cohort_result.scalars().all())
    if not cohort_user_ids:
        return None

    returned_result = await db.execute(
        select(func.count(func.distinct(UserDailyActivity.user_id))).where(
            UserDailyActivity.user_id.in_(cohort_user_ids),
            UserDailyActivity.activity_date == as_of,
        )
    )
    return round(returned_result.scalar_one() / len(cohort_user_ids), 4)


async def get_matches_per_user(db: AsyncSession) -> float:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if total_users == 0:
        return 0.0
    # MatchHistory already has one row PER USER per match (both directions
    # are written), so this is directly "total match-participations".
    total_participations = (await db.execute(select(func.count()).select_from(MatchHistory))).scalar_one()
    return round(total_participations / total_users, 2)


async def get_games_completed_per_user(db: AsyncSession) -> float:
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    if total_users == 0:
        return 0.0
    total_completed = (await db.execute(select(func.count()).select_from(UserMysteryHistory))).scalar_one()
    return round(total_completed / total_users, 2)


async def get_average_session_length_seconds(db: AsyncSession) -> float | None:
    """Across ALL outcomes (solved, failed, expired) — not just solves, which is
    what average_solve_seconds already covers. "Session" here means MysterySession:
    the time from being matched to the investigation reaching any terminal state."""
    result = await db.execute(
        select(func.avg(func.extract("epoch", MysterySession.ended_at - MysterySession.started_at))).where(
            MysterySession.ended_at.is_not(None)
        )
    )
    avg = result.scalar_one()
    return float(avg) if avg is not None else None


async def get_dau_trend(db: AsyncSession, days: int = 30) -> list[dict]:
    """Daily active users for each of the last `days` days, zero-filled so the
    chart has no gaps even on days nobody happened to log in."""
    as_of = utcnow().date()
    start = as_of - timedelta(days=days - 1)
    rows = (
        await db.execute(
            select(UserDailyActivity.activity_date, func.count(func.distinct(UserDailyActivity.user_id)))
            .where(UserDailyActivity.activity_date >= start, UserDailyActivity.activity_date <= as_of)
            .group_by(UserDailyActivity.activity_date)
        )
    ).all()
    counts_by_date = dict(rows)
    return [
        {"date": (start + timedelta(days=i)).isoformat(), "count": counts_by_date.get(start + timedelta(days=i), 0)}
        for i in range(days)
    ]


async def get_engagement_metrics(db: AsyncSession) -> dict:
    return {
        "dau": await get_dau(db),
        "mau": await get_mau(db),
        "d1_retention": await get_day_n_retention(db, 1),
        "d7_retention": await get_day_n_retention(db, 7),
        "d30_retention": await get_day_n_retention(db, 30),
        "matches_per_user": await get_matches_per_user(db),
        "games_completed_per_user": await get_games_completed_per_user(db),
        "average_session_length_seconds": await get_average_session_length_seconds(db),
        "dau_trend": await get_dau_trend(db),
    }
