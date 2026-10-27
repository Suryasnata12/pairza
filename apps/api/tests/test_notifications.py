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