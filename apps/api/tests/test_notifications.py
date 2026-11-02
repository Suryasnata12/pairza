import pytest
from sqlalchemy import select
import hashlib

from scripts import send_streak_reminders
from app.notifications import router as notifications_router
from app.notifications.models import PushSubscription
from app.notifications.schemas import PushSubscriptionCreate
from tests.conftest import make_user
from sqlalchemy.exc import IntegrityError
from app.notifications.models import PushReminderLog
from datetime import date, datetime, timedelta, timezone
from app.notifications.reminder_service import due_reminder_date
from scripts.send_streak_reminders import claim_reminder
from app.notifications.models import EngagementNotificationLog
from app.notifications.engagement_service import (
    claim_delivery_slot,
    get_local_delivery_slot,
)
from app.notifications import engagement_service
from app.common.redis_client import RedisKeys, get_redis
from app.matchmaking.models import Match
from app.sessions.models import MysterySession
from tests.conftest import make_mystery
from app.users.models import UserPreferences
import asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker
from types import SimpleNamespace
import uuid

async def test_subscription_is_saved_and_reassigned(db, monkeypatch):
    monkeypatch.setattr(
        notifications_router.settings,
        "VAPID_PUBLIC_KEY",
        "test-public-key",
    )
    monkeypatch.setattr(
        notifications_router.settings,
        "VAPID_PRIVATE_KEY",
        "test-private-key",
    )

    user_a = await make_user(db, "push_a@test.com", "push_a")
    user_b = await make_user(db, "push_b@test.com", "push_b")

    payload = PushSubscriptionCreate(
        endpoint="https://fcm.googleapis.com/fcm/send/test-endpoint",
        keys={
            "p256dh": "test-p256dh-key",
            "auth": "test-auth-key",
        },
    )

    await notifications_router.subscribe_push(payload, user_a, db)
    await notifications_router.subscribe_push(payload, user_b, db)

    rows = (
        await db.execute(select(PushSubscription))
    ).scalars().all()

    assert len(rows) == 1
    assert rows[0].user_id == user_b.id
    assert rows[0].endpoint == payload.endpoint


def test_non_https_or_unrecognized_push_endpoint_is_rejected():
    with pytest.raises(ValueError):
        PushSubscriptionCreate(
            endpoint="http://example.com/push",
            keys={"p256dh": "key", "auth": "auth"},
        )

async def test_streak_reminder_log_prevents_duplicate_for_same_local_day(db):
    user = await make_user(
        db,
        "reminder_log@test.com",
        "reminder_log_user",
    )

    first = PushReminderLog(
        user_id=user.id,
        reminder_date=date(2026, 10, 27),
        reminder_type="streak",
        status="pending",
        attempts=0,
    )
    db.add(first)
    await db.commit()

    duplicate = PushReminderLog(
        user_id=user.id,
        reminder_date=date(2026, 10, 27),
        reminder_type="streak",
        status="pending",
        attempts=0,
    )
    db.add(duplicate)

    with pytest.raises(IntegrityError):
        await db.commit()

    await db.rollback()

def test_streak_reminder_uses_users_local_evening():
    # 14:30 UTC is 20:00 in India.
    now = datetime(2026, 10, 27, 14, 30, tzinfo=timezone.utc)

    result = due_reminder_date(
        current_streak=3,
        last_active_date=date(2026, 10, 26),
        timezone_region="Asia/Calcutta",
        now_utc=now,
    )

    assert result == date(2026, 10, 27)


def test_streak_reminder_skips_before_local_evening():
    # 18:30 in India is too early for a reminder.
    now = datetime(2026, 10, 27, 13, 0, tzinfo=timezone.utc)

    result = due_reminder_date(
        current_streak=3,
        last_active_date=date(2026, 10, 26),
        timezone_region="Asia/Kolkata",
        now_utc=now,
    )

    assert result is None


def test_streak_reminder_skips_if_user_has_no_active_streak():
    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)

    result = due_reminder_date(
        current_streak=0,
        last_active_date=date(2026, 10, 26),
        timezone_region="Asia/Kolkata",
        now_utc=now,
    )

    assert result is None


def test_streak_reminder_skips_if_user_already_played_today():
    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)

    result = due_reminder_date(
        current_streak=3,
        last_active_date=date(2026, 10, 27),
        timezone_region="Asia/Kolkata",
        now_utc=now,
    )

    assert result is None

async def test_sent_streak_reminder_cannot_be_claimed_again(db):
    user = await make_user(
        db,
        "duplicate_reminder@test.com",
        "duplicate_reminder",
    )

    reminder_date = date(2026, 10, 27)
    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)

    # The first claim should succeed.
    first_id = await claim_reminder(
        db=db,
        user_id=user.id,
        reminder_date=reminder_date,
        now=now,
    )
    assert first_id is not None

    # Simulate the notification having been accepted and recorded.
    log = await db.get(PushReminderLog, first_id)
    assert log is not None

    log.status = "sent"
    log.sent_at = now
    log.updated_at = now
    await db.commit()

    # A subsequent run must not claim the same user/date/type again.
    second_id = await claim_reminder(
        db=db,
        user_id=user.id,
        reminder_date=reminder_date,
        now=now + timedelta(hours=1),
    )
    assert second_id is None

    # There must still be exactly one log for this reminder.
    result = await db.execute(
        select(PushReminderLog).where(
            PushReminderLog.user_id == user.id,
            PushReminderLog.reminder_date == reminder_date,
            PushReminderLog.reminder_type == "streak",
        )
    )
    logs = result.scalars().all()

    assert len(logs) == 1
    assert logs[0].status == "sent"
    assert logs[0].attempts == 1

async def test_failed_streak_reminder_retries_only_three_times(db):
    user = await make_user(
        db,
        "retry_reminder@test.com",
        "retry_reminder",
    )

    reminder_date = date(2026, 10, 27)
    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)

    # First attempt.
    first_id = await claim_reminder(
        db, user.id, reminder_date, now
    )
    assert first_id is not None

    log = await db.get(PushReminderLog, first_id)
    assert log is not None
    assert log.attempts == 1

    # Simulate a failed delivery.
    log.status = "failed"
    log.last_error = "Simulated failure"
    await db.commit()

    # Second attempt is allowed.
    second_id = await claim_reminder(
        db, user.id, reminder_date, now + timedelta(minutes=5)
    )
    assert second_id == first_id

    await db.refresh(log)
    assert log.attempts == 2
    assert log.status == "sending"

    # Simulate another failed delivery.
    log.status = "failed"
    await db.commit()

    # Third attempt is allowed.
    third_id = await claim_reminder(
        db, user.id, reminder_date, now + timedelta(minutes=10)
    )
    assert third_id == first_id

    await db.refresh(log)
    assert log.attempts == 3
    assert log.status == "sending"

    # After three attempts, no fourth attempt is allowed.
    log.status = "failed"
    await db.commit()

    fourth_id = await claim_reminder(
        db, user.id, reminder_date, now + timedelta(minutes=15)
    )
    assert fourth_id is None

    await db.refresh(log)
    assert log.attempts == 3
    assert log.status == "failed"

async def test_expired_push_subscription_is_deleted(db, monkeypatch):
    user = await make_user(
        db,
        "expired_push@test.com",
        "expired_push",
    )

    endpoint = "https://fcm.googleapis.com/fcm/send/expired-test"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    async def fake_send_to_subscription(_subscription):
        # Simulate a push provider reporting an expired subscription.
        return False, 410, "Push service returned HTTP 410"

    monkeypatch.setattr(
        send_streak_reminders,
        "send_to_subscription",
        fake_send_to_subscription,
    )

    now = datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc)
    entry = {
        "reminder_date": date(2026, 10, 27),
        "timezone_region": "Asia/Kolkata",
        "current_streak": 1,
        "subscriptions": [subscription],
    }

    sent, expired_count = await send_streak_reminders.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 1

    remaining = (
        await db.execute(
            select(PushSubscription).where(
                PushSubscription.id == subscription.id
            )
        )
    ).scalar_one_or_none()

    assert remaining is None

    log = (
        await db.execute(
            select(PushReminderLog).where(
                PushReminderLog.user_id == user.id,
                PushReminderLog.reminder_date == date(2026, 10, 27),
                PushReminderLog.reminder_type == "streak",
            )
        )
    ).scalar_one()

    assert log.status == "failed"
def test_engagement_delivery_windows():
    cases = [
        ("11:59", None),
        ("12:00", 1),
        ("14:59", 1),
        ("15:00", None),
        ("15:59", None),
        ("16:00", 2),
        ("18:59", 2),
        ("19:00", None),
    ]

    for clock, expected_slot in cases:
        hour, minute = map(int, clock.split(":"))
        now = datetime(
            2026, 11, 1, hour, minute,
            tzinfo=timezone.utc,
        )

        result = get_local_delivery_slot(
            "UTC",
            now,
        )

        if expected_slot is None:
            assert result is None
        else:
            assert result == (
                date(2026, 11, 1),
                expected_slot,
            )


async def test_engagement_slot_claim_retry_limit(db):
    user = await make_user(
        db,
        "engagement_claim@test.com",
        "engagement_claim",
    )

    local_date = date(2026, 11, 1)
    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    message = {
        "id": "test_message_001",
        "category": "challenge",
    }

    # First claim.
    first_id = await claim_delivery_slot(
        db, user.id, local_date, 1, message, now
    )
    assert first_id is not None

    log = await db.get(EngagementNotificationLog, first_id)
    assert log is not None
    assert log.attempts == 1
    assert log.status == "pending"

    # A pending claim cannot be claimed again immediately.
    duplicate_id = await claim_delivery_slot(
        db,
        user.id,
        local_date,
        1,
        message,
        now + timedelta(minutes=5),
    )
    assert duplicate_id is None

    # First failed attempt.
    log.status = "failed"
    await db.commit()

    # Second attempt.
    second_id = await claim_delivery_slot(
        db,
        user.id,
        local_date,
        1,
        message,
        now + timedelta(minutes=10),
    )
    assert second_id == first_id

    await db.refresh(log)
    assert log.attempts == 2
    assert log.status == "pending"

    # Second failed attempt.
    log.status = "failed"
    await db.commit()

    # Third attempt.
    third_id = await claim_delivery_slot(
        db,
        user.id,
        local_date,
        1,
        message,
        now + timedelta(minutes=15),
    )
    assert third_id == first_id

    await db.refresh(log)
    assert log.attempts == 3
    assert log.status == "pending"

    # Third failed attempt: no fourth attempt allowed.
    log.status = "failed"
    await db.commit()

    fourth_id = await claim_delivery_slot(
        db,
        user.id,
        local_date,
        1,
        message,
        now + timedelta(minutes=20),
    )

    assert fourth_id is None

    await db.refresh(log)
    assert log.attempts == 3
    assert log.status == "failed"

async def test_engagement_message_repeat_protection(db, monkeypatch):
    user = await make_user(
        db,
        "engagement_repeat@test.com",
        "engagement_repeat",
    )

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    message = {
        "id": "repeat_test_message",
        "category": "challenge",
        "body": "Test message",
        "url": "/home",
    }

    # Restrict the available message pool to one message.
    monkeypatch.setattr(
        engagement_service,
        "ENGAGEMENT_MESSAGES",
        (message,),
    )

    # A successful delivery 29 days ago must exclude it.
    recent_log = EngagementNotificationLog(
        user_id=user.id,
        local_date=date(2026, 10, 3),
        delivery_slot=1,
        message_id=message["id"],
        category=message["category"],
        status="sent",
        attempts=1,
        sent_at=now - timedelta(days=29),
    )

    db.add(recent_log)
    await db.commit()

    selected = await engagement_service.select_message(
        db,
        user.id,
        now,
    )

    assert selected is None

    # After 30 days, the same message becomes eligible again.
    recent_log.sent_at = now - timedelta(days=31)
    await db.commit()

    selected = await engagement_service.select_message(
        db,
        user.id,
        now,
    )

    assert selected is not None
    assert selected["id"] == message["id"]

async def test_engagement_detects_online_user(db):
    user = await make_user(
        db,
        "engagement_online@test.com",
        "engagement_online",
    )

    redis = get_redis()
    key = RedisKeys.PRESENCE_ONLINE.format(user_id=user.id)

    await redis.set(key, "1", ex=120)

    try:
        assert await engagement_service.is_user_online(user.id) is True

        await redis.delete(key)

        assert await engagement_service.is_user_online(user.id) is False
    finally:
        await redis.delete(key)

async def test_engagement_detects_active_mystery(db):
    user_a = await make_user(
        db,
        "engagement_player_a@test.com",
        "engagement_player_a",
    )

    user_b = await make_user(
        db,
        "engagement_player_b@test.com",
        "engagement_player_b",
    )

    mystery = await make_mystery(db)

    now = datetime.now(timezone.utc)

    match = Match(
        user_a_id=user_a.id,
        user_b_id=user_b.id,
        mystery_id=mystery.id,
        created_at=now,
    )
    db.add(match)
    await db.flush()

    session = MysterySession(
        match_id=match.id,
        mystery_id=mystery.id,
        player_a_id=user_a.id,
        player_b_id=user_b.id,
        status="ACTIVE",
        current_stage_number=1,
        started_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(minutes=10),
    )

    db.add(session)
    await db.commit()

    # ACTIVE session must suppress notifications.
    assert await engagement_service.has_active_mystery(
        db,
        user_a.id,
        now,
    ) is True

    # WAITING session must also suppress notifications.
    session.status = "WAITING"
    await db.commit()

    assert await engagement_service.has_active_mystery(
        db,
        user_a.id,
        now,
    ) is True

    # A terminal session must not suppress notifications.
    session.status = "SOLVED"
    await db.commit()

    assert await engagement_service.has_active_mystery(
        db,
        user_a.id,
        now,
    ) is False

    # An expired ACTIVE session must not suppress notifications.
    session.status = "ACTIVE"
    session.expires_at = now - timedelta(minutes=1)
    await db.commit()

    assert await engagement_service.has_active_mystery(
        db,
        user_a.id,
        now,
    ) is False

async def test_engagement_releases_claim_if_user_becomes_online(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_release@test.com",
        "engagement_release",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    preferences.engagement_notifications_enabled = True

    endpoint = "https://fcm.googleapis.com/fcm/send/engagement-release"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )

    db.add(subscription)
    await db.commit()

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(
        engagement_service,
        "utcnow",
        lambda: now,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    message = {
        "id": "engagement_release_test",
        "category": "challenge",
        "body": "A test notification",
        "url": "/home",
    }

    # Ensure rollout is enabled only within this test.
    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    # Initially offline; online during the final suppression check.
    presence_checks = 0

    async def fake_is_user_online(user_id):
        nonlocal presence_checks
        presence_checks += 1
        return presence_checks >= 2

    monkeypatch.setattr(
        engagement_service,
        "is_user_online",
        fake_is_user_online,
    )

    async def fake_select_message(db, user_id, current_time):
        return message

    monkeypatch.setattr(
        engagement_service,
        "select_message",
        fake_select_message,
    )

    async def unexpected_push(*args, **kwargs):
        raise AssertionError(
            "Push must not be sent after the user becomes online"
        )

    monkeypatch.setattr(
        engagement_service,
        "send_to_subscription",
        unexpected_push,
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 0
    assert presence_checks == 2

    # The suppressed claim must be released, not marked failed.
    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == date(2026, 11, 1),
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalars().all()

    assert logs == []

async def test_engagement_concurrent_claims_allow_only_one_worker(db):
    user = await make_user(
        db,
        "engagement_concurrent@test.com",
        "engagement_concurrent",
    )

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    local_date = date(2026, 11, 1)

    message = {
        "id": "engagement_concurrent_test",
        "category": "challenge",
    }

    # Use two independent database sessions to simulate two workers.
    session_factory = async_sessionmaker(
        bind=db.bind,
        expire_on_commit=False,
    )

    async def attempt_claim():
        async with session_factory() as worker_db:
            return await claim_delivery_slot(
                db=worker_db,
                user_id=user.id,
                local_date=local_date,
                delivery_slot=1,
                message=message,
                now=now,
            )

    results = await asyncio.gather(
        attempt_claim(),
        attempt_claim(),
    )

    successful_claims = [
        result for result in results if result is not None
    ]

    assert len(successful_claims) == 1

    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == local_date,
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalars().all()

    assert len(logs) == 1
    assert logs[0].status == "pending"
    assert logs[0].attempts == 1

async def test_engagement_releases_claim_if_user_enters_mystery(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_active_release@test.com",
        "engagement_active_release",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    preferences.engagement_notifications_enabled = True

    endpoint = "https://fcm.googleapis.com/fcm/send/active-release"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )
    db.add(subscription)
    await db.commit()

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(
        engagement_service,
        "utcnow",
        lambda: now,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    message = {
        "id": "engagement_active_release_test",
        "category": "challenge",
        "body": "A test notification",
        "url": "/home",
    }

    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    # The first check finds no active mystery.
    # The final check finds one.
    active_checks = 0

    async def fake_has_active_mystery(db, user_id, current_time):
        nonlocal active_checks
        active_checks += 1
        return active_checks >= 2

    monkeypatch.setattr(
        engagement_service,
        "has_active_mystery",
        fake_has_active_mystery,
    )

    async def fake_is_user_online(user_id):
        return False

    monkeypatch.setattr(
        engagement_service,
        "is_user_online",
        fake_is_user_online,
    )

    async def fake_select_message(db, user_id, current_time):
        return message

    monkeypatch.setattr(
        engagement_service,
        "select_message",
        fake_select_message,
    )

    async def unexpected_push(*args, **kwargs):
        raise AssertionError(
            "Push must not be sent when a mystery becomes active"
        )

    monkeypatch.setattr(
        engagement_service,
        "send_to_subscription",
        unexpected_push,
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 0
    assert active_checks == 2

    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == date(2026, 11, 1),
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalars().all()

    assert logs == []

async def test_engagement_successful_delivery_marks_log_sent(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_success@test.com",
        "engagement_success",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()
    preferences.engagement_notifications_enabled = True

    endpoint = "https://fcm.googleapis.com/fcm/send/engagement-success"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )
    db.add(subscription)
    await db.commit()

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(
        engagement_service,
        "utcnow",
        lambda: now,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    message = {
        "id": "engagement_success_test",
        "category": "challenge",
        "body": "A test notification",
        "url": "/home",
    }

    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    async def fake_is_user_online(user_id):
        return False

    async def fake_has_active_mystery(db, user_id, current_time):
        return False

    async def fake_select_message(db, user_id, current_time):
        return message

    async def fake_send_to_subscription(subscription, payload):
        assert payload["title"] == "Pairza"
        assert payload["body"] == message["body"]
        assert payload["tag"] == "pairza-engagement"
        return True, 201, None

    monkeypatch.setattr(
        engagement_service, "is_user_online", fake_is_user_online
    )
    monkeypatch.setattr(
        engagement_service, "has_active_mystery", fake_has_active_mystery
    )
    monkeypatch.setattr(
        engagement_service, "select_message", fake_select_message
    )
    monkeypatch.setattr(
        engagement_service, "send_to_subscription",
        fake_send_to_subscription,
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is True
    assert expired_count == 0

    log = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == date(2026, 11, 1),
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalar_one()

    assert log.status == "sent"
    assert log.sent_at is not None
    assert log.attempts == 1
    assert log.message_id == message["id"]

async def test_engagement_expired_subscription_is_deleted(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_expired@test.com",
        "engagement_expired",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()
    preferences.engagement_notifications_enabled = True

    endpoint = "https://fcm.googleapis.com/fcm/send/engagement-expired"
    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )
    db.add(subscription)
    await db.commit()
    await db.refresh(subscription)

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )
    monkeypatch.setattr(
        engagement_service,
        "utcnow",
        lambda: now,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    message = {
        "id": "engagement_expired_test",
        "category": "challenge",
        "body": "A test notification",
        "url": "/home",
    }

    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    async def fake_is_user_online(user_id):
        return False

    async def fake_has_active_mystery(db, user_id, current_time):
        return False

    async def fake_select_message(db, user_id, current_time):
        return message

    async def fake_send_to_subscription(subscription, payload):
        return False, 410, "Push service returned HTTP 410"

    monkeypatch.setattr(
        engagement_service, "is_user_online", fake_is_user_online
    )
    monkeypatch.setattr(
        engagement_service, "has_active_mystery", fake_has_active_mystery
    )
    monkeypatch.setattr(
        engagement_service, "select_message", fake_select_message
    )
    monkeypatch.setattr(
        engagement_service, "send_to_subscription",
        fake_send_to_subscription,
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 1

    remaining_subscription = await db.get(
        PushSubscription,
        subscription.id,
    )
    assert remaining_subscription is None

    log = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == date(2026, 11, 1),
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalar_one()

    assert log.status == "failed"
    assert log.attempts == 1
    assert log.sent_at is None

def test_engagement_rollout_fails_closed(monkeypatch):
    user_id = uuid.uuid4()
    now = datetime(2026, 11, 1, 12, 30, tzinfo=timezone.utc)

    settings = SimpleNamespace(
        ENGAGEMENT_NOTIFICATIONS_MODE="off",
        ENGAGEMENT_NOTIFICATIONS_ALLOWLIST="",
        ENGAGEMENT_NOTIFICATIONS_TEST_END_AT=now + timedelta(days=7),
    )

    monkeypatch.setattr(
        engagement_service,
        "get_settings",
        lambda: settings,
    )

    assert engagement_service.is_rollout_enabled(user_id, now) is False

    # Allowlist mode: only the selected user is eligible.
    settings.ENGAGEMENT_NOTIFICATIONS_MODE = "allowlist"
    settings.ENGAGEMENT_NOTIFICATIONS_ALLOWLIST = str(user_id)

    assert engagement_service.is_rollout_enabled(user_id, now) is True
    assert engagement_service.is_rollout_enabled(uuid.uuid4(), now) is False

    # Missing expiry must fail closed.
    settings.ENGAGEMENT_NOTIFICATIONS_TEST_END_AT = None

    assert engagement_service.is_rollout_enabled(user_id, now) is False

    # Expired rollout must fail closed.
    settings.ENGAGEMENT_NOTIFICATIONS_TEST_END_AT = now - timedelta(seconds=1)

    assert engagement_service.is_rollout_enabled(user_id, now) is False

    # Invalid mode must fail closed.
    settings.ENGAGEMENT_NOTIFICATIONS_MODE = "unexpected"

    assert engagement_service.is_rollout_enabled(user_id, now) is False

async def test_engagement_collection_respects_consent_and_account_status(
    db,
    monkeypatch,
):
    eligible = await make_user(
        db, "eligible@test.com", "eligible_user"
    )
    opted_out = await make_user(
        db, "optedout@test.com", "optedout_user"
    )
    inactive = await make_user(
        db, "inactive@test.com", "inactive_user"
    )
    suspended = await make_user(
        db, "suspended@test.com", "suspended_user"
    )
    banned = await make_user(
        db, "banned@test.com", "banned_user"
    )
    no_subscription = await make_user(
        db, "nosub@test.com", "nosub_user"
    )

    # Explicitly enable promotional consent for everyone except opted_out.
    eligible_users = [
        eligible,
        inactive,
        suspended,
        banned,
        no_subscription,
    ]

    for user in eligible_users:
        preferences = (
            await db.execute(
                select(UserPreferences).where(
                    UserPreferences.user_id == user.id
                )
            )
        ).scalar_one()

        preferences.engagement_notifications_enabled = True

    # Test account-status exclusions.
    inactive.is_active = False
    suspended.is_suspended = True
    banned.is_banned = True

    # Add subscriptions to everyone except no_subscription.
    subscribed_users = [
        eligible,
        opted_out,
        inactive,
        suspended,
        banned,
    ]

    for index, user in enumerate(subscribed_users):
        endpoint = (
            f"https://fcm.googleapis.com/fcm/send/"
            f"eligibility-test-{index}"
        )

        db.add(
            PushSubscription(
                user_id=user.id,
                endpoint=endpoint,
                endpoint_hash=hashlib.sha256(
                    endpoint.encode("utf-8")
                ).hexdigest(),
                p256dh_key="test-p256dh-key",
                auth_key="test-auth-key",
            )
        )

    await db.commit()

    # Isolate collection eligibility from rollout configuration.
    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    due_users = await engagement_service.collect_due_users(
        db,
        now,
    )

    # Only the opted-in, active, eligible account with a subscription
    # should be collected.
    assert set(due_users.keys()) == {eligible.id}

    assert due_users[eligible.id]["local_date"] == date(2026, 11, 1)
    assert due_users[eligible.id]["delivery_slot"] == 1
    assert len(due_users[eligible.id]["subscriptions"]) == 1

async def test_engagement_skips_user_who_revokes_consent_before_delivery(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_revoked@test.com",
        "engagement_revoked",
    )

    # User has opted out before processing begins.
    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    preferences.engagement_notifications_enabled = False
    await db.commit()

    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [],
    }

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 0

    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
            )
        )
    ).scalars().all()

    assert logs == []

@pytest.mark.parametrize(
    "suppression_case",
    ["rollout_expired", "consent_revoked", "window_closed"],
)
async def test_engagement_releases_claim_when_final_eligibility_changes(
    db,
    monkeypatch,
    suppression_case,
):
    user = await make_user(
        db,
        f"engagement_final_{suppression_case}@test.com",
        f"engagement_final_{suppression_case}",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    preferences.engagement_notifications_enabled = True

    endpoint = (
        f"https://fcm.googleapis.com/fcm/send/{suppression_case}"
    )

    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )

    db.add(subscription)
    await db.commit()

    now = datetime(
        2026, 11, 1, 12, 30,
        tzinfo=timezone.utc,
    )

    entry = {
        "local_date": date(2026, 11, 1),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    message = {
        "id": f"final_check_{suppression_case}",
        "category": "challenge",
        "body": "A test notification",
        "url": "/home",
    }

    rollout_checks = 0

    def fake_rollout(user_id, current_time):
        nonlocal rollout_checks
        rollout_checks += 1

        if suppression_case == "rollout_expired":
            return rollout_checks == 1

        return True

    def fake_utcnow():
        if suppression_case == "consent_revoked":
            preferences.engagement_notifications_enabled = False

        if suppression_case == "window_closed":
            return now + timedelta(hours=2, minutes=30)

        return now

    async def fake_is_user_online(user_id):
        return False

    async def fake_has_active_mystery(db, user_id, current_time):
        return False

    async def fake_select_message(db, user_id, current_time):
        return message

    async def unexpected_push(*args, **kwargs):
        raise AssertionError(
            "Push must not be sent after final eligibility fails"
        )

    monkeypatch.setattr(
        engagement_service, "is_rollout_enabled", fake_rollout
    )
    monkeypatch.setattr(
        engagement_service, "utcnow", fake_utcnow
    )
    monkeypatch.setattr(
        engagement_service, "is_user_online", fake_is_user_online
    )
    monkeypatch.setattr(
        engagement_service, "has_active_mystery",
        fake_has_active_mystery,
    )
    monkeypatch.setattr(
        engagement_service, "select_message", fake_select_message
    )
    monkeypatch.setattr(
        engagement_service, "send_to_subscription", unexpected_push
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
    )

    assert sent is False
    assert expired_count == 0

    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
                EngagementNotificationLog.local_date == date(2026, 11, 1),
                EngagementNotificationLog.delivery_slot == 1,
            )
        )
    ).scalars().all()

    assert logs == []

async def test_engagement_dry_run_does_not_claim_or_send(
    db,
    monkeypatch,
):
    user = await make_user(
        db,
        "engagement_dryrun@test.com",
        "engagement_dryrun",
    )

    preferences = (
        await db.execute(
            select(UserPreferences).where(
                UserPreferences.user_id == user.id
            )
        )
    ).scalar_one()

    preferences.engagement_notifications_enabled = True

    endpoint = "https://fcm.googleapis.com/fcm/send/engagement-dryrun"

    subscription = PushSubscription(
        user_id=user.id,
        endpoint=endpoint,
        endpoint_hash=hashlib.sha256(
            endpoint.encode("utf-8")
        ).hexdigest(),
        p256dh_key="test-p256dh-key",
        auth_key="test-auth-key",
    )

    db.add(subscription)
    await db.commit()

    now = datetime(
        2026, 11, 2, 12, 30,
        tzinfo=timezone.utc,
    )

    entry = {
        "local_date": date(2026, 11, 2),
        "delivery_slot": 1,
        "timezone_region": "UTC",
        "subscriptions": [subscription],
    }

    monkeypatch.setattr(
        engagement_service,
        "is_rollout_enabled",
        lambda user_id, current_time: True,
    )

    async def fake_is_user_online(user_id):
        return False

    async def fake_has_active_mystery(db, user_id, current_time):
        return False

    async def fake_select_message(db, user_id, current_time):
        return {
            "id": "dryrun_message",
            "category": "challenge",
            "body": "Dry-run test",
            "url": "/home",
        }

    async def unexpected_claim(*args, **kwargs):
        raise AssertionError("Dry-run must not claim a delivery slot")

    async def unexpected_push(*args, **kwargs):
        raise AssertionError("Dry-run must not send a push")

    monkeypatch.setattr(
        engagement_service, "is_user_online", fake_is_user_online
    )
    monkeypatch.setattr(
        engagement_service, "has_active_mystery",
        fake_has_active_mystery,
    )
    monkeypatch.setattr(
        engagement_service, "select_message", fake_select_message
    )
    monkeypatch.setattr(
        engagement_service, "claim_delivery_slot", unexpected_claim
    )
    monkeypatch.setattr(
        engagement_service, "send_to_subscription", unexpected_push
    )

    sent, expired_count = await engagement_service.process_user(
        db=db,
        user_id=user.id,
        entry=entry,
        now=now,
        dry_run=True,
    )

    assert sent is False
    assert expired_count == 0

    logs = (
        await db.execute(
            select(EngagementNotificationLog).where(
                EngagementNotificationLog.user_id == user.id,
            )
        )
    ).scalars().all()

    assert logs == []