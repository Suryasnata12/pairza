from datetime import timedelta

from app.admin import service as admin_service
from app.common.mixins import utcnow
from app.users.models import UserDailyActivity
from tests.conftest import make_user


async def _log_activity(db, user_id, days_ago: int):
    db.add(UserDailyActivity(user_id=user_id, activity_date=utcnow().date() - timedelta(days=days_ago)))


async def test_dau_counts_distinct_users_active_today(db):
    a = await make_user(db, "dau_a@test.com", "dau_a")
    b = await make_user(db, "dau_b@test.com", "dau_b")
    c = await make_user(db, "dau_c@test.com", "dau_c")
    await _log_activity(db, a.id, days_ago=0)
    await _log_activity(db, b.id, days_ago=0)
    await _log_activity(db, c.id, days_ago=1)  # yesterday, not today
    await db.commit()

    assert await admin_service.get_dau(db) == 2


async def test_dau_deduplicates_multiple_events_same_day(db):
    """The whole point of ON CONFLICT DO NOTHING — recording the same user
    twice in one day (every poll, every page load) must not inflate DAU.
    This calls the real production upsert function directly, not the raw
    ORM-insert test helper, since that's the actual behavior being verified."""
    from app.users.service import record_daily_activity

    a = await make_user(db, "dau_dup@test.com", "dau_dup")
    await record_daily_activity(a.id)
    await record_daily_activity(a.id)  # same user, same day, "recorded" twice

    assert await admin_service.get_dau(db) == 1


async def test_mau_counts_distinct_users_in_last_30_days(db):
    a = await make_user(db, "mau_a@test.com", "mau_a")
    b = await make_user(db, "mau_b@test.com", "mau_b")
    await _log_activity(db, a.id, days_ago=5)
    await _log_activity(db, b.id, days_ago=29)  # exactly at the edge, still counts
    await db.commit()

    assert await admin_service.get_mau(db) == 2


async def test_mau_excludes_activity_older_than_30_days(db):
    a = await make_user(db, "mau_old@test.com", "mau_old")
    await _log_activity(db, a.id, days_ago=31)
    await db.commit()

    assert await admin_service.get_mau(db) == 0


async def test_d1_retention_counts_users_who_returned_the_next_day(db):
    returner = await make_user(db, "ret_yes@test.com", "ret_yes")
    churner = await make_user(db, "ret_no@test.com", "ret_no")

    # Both users' FIRST-EVER activity was exactly 1 day ago (the cohort day).
    await _log_activity(db, returner.id, days_ago=1)
    await _log_activity(db, churner.id, days_ago=1)
    # Only the returner came back today.
    await _log_activity(db, returner.id, days_ago=0)
    await db.commit()

    retention = await admin_service.get_day_n_retention(db, n=1)
    assert retention == 0.5  # 1 of 2 in that cohort returned


async def test_retention_excludes_users_whose_first_day_was_earlier(db):
    """A user first seen 5 days ago shouldn't count in the D1 cohort just
    because they also happened to be active yesterday and today."""
    long_timer = await make_user(db, "longtimer@test.com", "longtimer")
    await _log_activity(db, long_timer.id, days_ago=5)  # this is their FIRST day, not the D1 cohort day
    await _log_activity(db, long_timer.id, days_ago=1)
    await _log_activity(db, long_timer.id, days_ago=0)
    await db.commit()

    # D1 cohort = users whose first day was exactly 1 day ago. This user's
    # first day was 5 days ago, so they don't belong to that cohort at all.
    retention = await admin_service.get_day_n_retention(db, n=1)
    assert retention is None


async def test_retention_is_none_when_cohort_is_empty(db):
    """No data yet is a different fact from 0% retention — must not be
    conflated, or an early-days product looks like it's failing to retain
    users it simply hasn't had yet."""
    assert await admin_service.get_day_n_retention(db, n=7) is None


async def test_matches_per_user_averages_across_all_users(db):
    from app.matchmaking.models import Match, MatchHistory
    from tests.conftest import make_mystery

    mystery = await make_mystery(db)
    a = await make_user(db, "mpu_a@test.com", "mpu_a")
    b = await make_user(db, "mpu_b@test.com", "mpu_b")

    match = Match(user_a_id=a.id, user_b_id=b.id, mystery_id=mystery.id, created_at=utcnow())
    db.add(match)
    await db.flush()

    # Two MatchHistory rows (one per direction) = two "participations" total, across 2 users -> 1.0 per user.
    db.add(MatchHistory(user_id=a.id, matched_with_user_id=b.id, match_id=match.id, created_at=utcnow()))
    db.add(MatchHistory(user_id=b.id, matched_with_user_id=a.id, match_id=match.id, created_at=utcnow()))
    await db.commit()

    assert await admin_service.get_matches_per_user(db) == 1.0


async def test_average_session_length_only_counts_sessions_with_ended_at(db):
    from tests.test_sessions import _create_session_directly
    from tests.conftest import make_mystery

    mystery = await make_mystery(db)
    a = await make_user(db, "asl_a@test.com", "asl_a")
    b = await make_user(db, "asl_b@test.com", "asl_b")

    session = await _create_session_directly(db, mystery, a, b)
    session.ended_at = session.started_at + timedelta(minutes=10)
    await db.commit()

    avg = await admin_service.get_average_session_length_seconds(db)
    assert avg == 600.0  # exactly 10 minutes, and it's the only ended session


async def test_average_session_length_is_none_with_no_ended_sessions(db):
    assert await admin_service.get_average_session_length_seconds(db) is None
