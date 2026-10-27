
"""
Scheduled Pairza streak reminder sender.

Run from apps/api:
    python -m scripts.send_streak_reminders --dry-run
    python -m scripts.send_streak_reminders

The dry run never sends pushes or creates reminder log records.
"""

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from pywebpush import WebPushException, webpush
from sqlalchemy import and_, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.common.database import AsyncSessionLocal
from app.config.settings import get_settings
from app.notifications.models import PushReminderLog, PushSubscription
from app.notifications.reminder_service import due_reminder_date
from app.users.models import Profile, User, UserPreferences


logger = logging.getLogger("pairza.streak_reminders")

REMINDER_TYPE = "streak"
MAX_ATTEMPTS = 3

# A crashed job that left a record in "sending" can be retried after this.
STALE_SENDING_MINUTES = 30

PUSH_PAYLOAD = {
    "title": "Protect your Pairza streak",
    "body": "Your streak is waiting. Solve a mystery before today ends.",
    "url": "/home",
    "tag": "pairza-streak-reminder",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def collect_due_users(db, now: datetime) -> dict:
    """
    Return eligible users grouped by user ID.

    A user is eligible only when:
    - the account is active and not suspended or banned;
    - notifications are enabled;
    - the streak is positive;
    - the last activity was yesterday in the user's timezone;
    - the user's local time is in the reminder window;
    - at least one push subscription exists.
    """

    stmt = (
        select(
            User.id,
            Profile.current_streak,
            Profile.last_active_date,
            UserPreferences.timezone_region,
            PushSubscription,
        )
        .join(Profile, Profile.user_id == User.id)
        .join(UserPreferences, UserPreferences.user_id == User.id)
        .join(PushSubscription, PushSubscription.user_id == User.id)
        .where(
            User.is_active.is_(True),
            User.is_suspended.is_(False),
            User.is_banned.is_(False),
            UserPreferences.notifications_enabled.is_(True),
            Profile.current_streak > 0,
        )
    )

    rows = (await db.execute(stmt)).all()
    due_users = {}

    for user_id, streak, last_active, timezone_region, subscription in rows:
        reminder_date = due_reminder_date(
            current_streak=streak,
            last_active_date=last_active,
            timezone_region=timezone_region,
            now_utc=now,
        )

        if reminder_date is None:
            continue

        entry = due_users.setdefault(
            user_id,
            {
                "reminder_date": reminder_date,
                "timezone_region": timezone_region or "UTC",
                "current_streak": streak,
                "subscriptions": [],
            },
        )

        entry["subscriptions"].append(subscription)

    return due_users


async def claim_reminder(
    db,
    user_id: uuid.UUID,
    reminder_date,
    now: datetime,
) -> uuid.UUID | None:
    """
    Atomically claim a reminder for one user and local calendar date.

    The unique database constraint prevents two overlapping jobs from
    creating separate log entries for the same user/day/type.

    Failed attempts and stale "sending" records can be retried, up to
    MAX_ATTEMPTS. A successfully sent reminder is never claimed again.
    """

    new_id = uuid.uuid4()

    insert_stmt = (
        pg_insert(PushReminderLog)
        .values(
            id=new_id,
            user_id=user_id,
            reminder_date=reminder_date,
            reminder_type=REMINDER_TYPE,
            status="sending",
            attempts=1,
            sent_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            constraint="uq_push_reminder_user_date_type"
        )
        .returning(PushReminderLog.id)
    )

    inserted_id = (await db.execute(insert_stmt)).scalar_one_or_none()
    await db.commit()

    if inserted_id is not None:
        return inserted_id

    # A log already exists. Retry only a failed/pending attempt or a
    # stale in-progress attempt, and only while the attempt budget remains.
    stale_before = now - timedelta(minutes=STALE_SENDING_MINUTES)

    retry_condition = or_(
        PushReminderLog.status.in_(("pending", "failed")),
        and_(
            PushReminderLog.status == "sending",
            PushReminderLog.updated_at < stale_before,
        ),
    )

    retry_stmt = (
        update(PushReminderLog)
        .where(
            PushReminderLog.user_id == user_id,
            PushReminderLog.reminder_date == reminder_date,
            PushReminderLog.reminder_type == REMINDER_TYPE,
            PushReminderLog.attempts < MAX_ATTEMPTS,
            retry_condition,
        )
        .values(
            status="sending",
            attempts=PushReminderLog.attempts + 1,
            sent_at=None,
            last_error=None,
            updated_at=now,
        )
        .returning(PushReminderLog.id)
    )

    claimed_id = (await db.execute(retry_stmt)).scalar_one_or_none()
    await db.commit()
    return claimed_id


async def send_to_subscription(subscription: PushSubscription) -> tuple[bool, int | None, str | None]:
    """Send one notification without logging subscription secrets."""

    settings = get_settings()

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {
            "p256dh": subscription.p256dh_key,
            "auth": subscription.auth_key,
        },
    }

    try:
        response = await asyncio.to_thread(
            webpush,
            subscription_info=subscription_info,
            data=json.dumps(PUSH_PAYLOAD),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=300,
        )

        if 200 <= response.status_code < 300:
            return True, response.status_code, None

        return False, response.status_code, f"Push service returned HTTP {response.status_code}"

    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

        # Do not include the exception text: it may contain endpoint details.
        message = (
            f"Push service returned HTTP {status_code}"
            if status_code is not None
            else "Push request failed"
        )
        return False, status_code, message

    except Exception:
        logger.exception("Unexpected push delivery error")
        return False, None, "Unexpected push delivery error"


async def process_user(
    db,
    user_id: uuid.UUID,
    entry: dict,
    now: datetime,
) -> tuple[bool, int]:
    """
    Claim and send one user's reminder across their saved subscriptions.

    Returns (accepted_by_at_least_one_push_service, expired_subscription_count).
    """

    log_id = await claim_reminder(
        db=db,
        user_id=user_id,
        reminder_date=entry["reminder_date"],
        now=now,
    )

    if log_id is None:
        logger.info("Skipping user %s: already sent, claimed, or retry limit reached", user_id)
        return False, 0

    accepted_count = 0
    expired_ids = []
    errors = []
    subscriptions = entry["subscriptions"]

    for subscription in subscriptions:
        ok, status_code, error = await send_to_subscription(subscription)

        if ok:
            accepted_count += 1
            continue

        if status_code in (404, 410):
            expired_ids.append(subscription.id)
            continue

        if error:
            errors.append(error)

    # Remove subscriptions that the push provider says are no longer valid.
    if expired_ids:
        from sqlalchemy import delete

        await db.execute(
            delete(PushSubscription).where(
                PushSubscription.id.in_(expired_ids)
            )
        )

    log = await db.get(PushReminderLog, log_id)

    if log is not None:
        log.updated_at = utcnow()

        if accepted_count:
            # A successful provider acceptance counts as sent, even if another
            # device's subscription failed. Do not resend to every device next hour.
            log.status = "sent"
            log.sent_at = utcnow()
            log.last_error = None
        else:
            log.status = "failed"
            log.sent_at = None
            log.last_error = (
                "; ".join(errors) or "No push service accepted the notification"
            )[:500]

        await db.commit()

    return accepted_count > 0, len(expired_ids)


async def run(dry_run: bool = False) -> None:
    settings = get_settings()

    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        raise RuntimeError("VAPID keys are not configured.")

    if not settings.VAPID_SUBJECT:
        raise RuntimeError("VAPID_SUBJECT is not configured.")

    now = utcnow()
    logger.info("Connecting to database...") #temp

    async with AsyncSessionLocal() as db:
        logger.info("Connected. Checking eligible users...") #temp
        due_users = await collect_due_users(db, now)

        logger.info("Eligibility query completed.") #temp
        logger.info(
            "Reminder check at %s UTC: %d eligible user(s)",
            now.isoformat(),
            len(due_users),
        )

        if dry_run:
            # Deliberately does not claim logs, alter subscriptions, or send pushes.
            for entry in due_users.values():
                logger.info(
                    "Dry run: eligible local date=%s, timezone=%s, streak=%d, subscriptions=%d",
                    entry["reminder_date"],
                    entry["timezone_region"],
                    entry["current_streak"],
                    len(entry["subscriptions"]),
                )

            logger.info("Dry run complete. No notifications were sent.")
            return

        sent_users = 0
        skipped_or_failed = 0
        expired_subscriptions = 0

        for user_id, entry in due_users.items():
            try:
                sent, expired_count = await process_user(
                    db=db,
                    user_id=user_id,
                    entry=entry,
                    now=now,
                )
                expired_subscriptions += expired_count

                if sent:
                    sent_users += 1
                else:
                    skipped_or_failed += 1

            except Exception:
                await db.rollback()
                logger.exception("Failed to process reminder for user %s", user_id)
                skipped_or_failed += 1

        logger.info(
            "Reminder run finished: accepted=%d, skipped_or_failed=%d, expired_subscriptions_removed=%d",
            sent_users,
            skipped_or_failed,
            expired_subscriptions,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Send Pairza streak reminders.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List eligible users without sending pushes or creating log records.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
