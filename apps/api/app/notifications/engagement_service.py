
"""Pairza promotional engagement notification service."""

import asyncio
import json
import logging
import random
import uuid

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pywebpush import WebPushException, webpush
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.common.database import AsyncSessionLocal
from app.common.redis_client import RedisKeys, get_redis
from app.config.settings import get_settings
from app.notifications.engagement_messages import ENGAGEMENT_MESSAGES
from app.notifications.models import (
    EngagementNotificationLog,
    PushSubscription,
)
from app.sessions.models import MysterySession
from app.users.models import User, UserPreferences

logger = logging.getLogger("pairza.engagement_notifications")

MAX_ATTEMPTS = 3
STALE_PENDING_MINUTES = 30
MESSAGE_REPEAT_DAYS = 30

DELIVERY_WINDOWS = {
    1: (time(12, 0), time(15, 0)),
    2: (time(16, 0), time(19, 0)),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_user_timezone(timezone_region: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(timezone_region or "UTC")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


def get_local_delivery_slot(
    timezone_region: str | None,
    now: datetime,
) -> tuple[date, int] | None:
    """Return the local date and slot if now is inside an approved window."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    local_now = now.astimezone(get_user_timezone(timezone_region))
    local_time = local_now.time().replace(tzinfo=None)

    for slot, (start, end) in DELIVERY_WINDOWS.items():
        if start <= local_time < end:
            return local_now.date(), slot

    return None


def is_rollout_enabled(user_id: uuid.UUID, now: datetime) -> bool:
    """Fail closed unless the rollout is explicitly configured."""

    settings = get_settings()
    mode = settings.ENGAGEMENT_NOTIFICATIONS_MODE.strip().lower()

    if mode == "off":
        return False

    # The test must have an explicit expiry.
    expiry = settings.ENGAGEMENT_NOTIFICATIONS_TEST_END_AT
    if expiry is None:
        return False

    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)

    if now >= expiry:
        return False

    if mode == "allowlist":
        raw_ids = settings.ENGAGEMENT_NOTIFICATIONS_ALLOWLIST
        allowed_ids = set()

        for value in raw_ids.split(","):
            value = value.strip()
            if not value:
                continue

            try:
                allowed_ids.add(uuid.UUID(value))
            except ValueError:
                logger.warning("Ignoring invalid engagement allowlist UUID")

        return user_id in allowed_ids

    if mode == "all":
        return True

    logger.error("Invalid engagement notification mode: %s", mode)
    return False


async def is_user_online(user_id: uuid.UUID) -> bool:
    """Redis is the authoritative source for online presence."""

    redis = get_redis()
    key = RedisKeys.PRESENCE_ONLINE.format(user_id=user_id)
    return bool(await redis.exists(key))


async def has_active_mystery(db, user_id: uuid.UUID, now: datetime) -> bool:
    """WAITING and ACTIVE sessions both suppress promotional notifications."""

    result = await db.execute(
        select(MysterySession.id)
        .where(
            MysterySession.status.in_(("WAITING", "ACTIVE")),
            MysterySession.expires_at > now,
            or_(
                MysterySession.player_a_id == user_id,
                MysterySession.player_b_id == user_id,
            ),
        )
        .limit(1)
    )

    return result.scalar_one_or_none() is not None


async def select_message(
    db,
    user_id: uuid.UUID,
    now: datetime,
) -> dict | None:
    """Choose a message not successfully sent to this user in 30 days."""

    cutoff = now - timedelta(days=MESSAGE_REPEAT_DAYS)

    result = await db.execute(
        select(EngagementNotificationLog.message_id)
        .where(
            EngagementNotificationLog.user_id == user_id,
            EngagementNotificationLog.status == "sent",
            EngagementNotificationLog.sent_at >= cutoff,
        )
    )

    recently_sent = set(result.scalars().all())

    available = [
        message
        for message in ENGAGEMENT_MESSAGES
        if message["id"] not in recently_sent
    ]

    if not available:
        logger.warning("No unused engagement messages available for user %s", user_id)
        return None

    return random.choice(available)


async def collect_due_users(db, now: datetime) -> dict:
    """Collect opted-in users currently inside an approved local delivery window."""

    stmt = (
        select(
            User.id,
            UserPreferences.timezone_region,
            PushSubscription,
        )
        .join(
            UserPreferences,
            UserPreferences.user_id == User.id,
        )
        .join(
            PushSubscription,
            PushSubscription.user_id == User.id,
        )
        .where(
            User.is_active.is_(True),
            User.is_suspended.is_(False),
            User.is_banned.is_(False),
            UserPreferences.engagement_notifications_enabled.is_(True),
        )
    )

    rows = (await db.execute(stmt)).all()
    due_users = {}

    for user_id, timezone_region, subscription in rows:
        if not is_rollout_enabled(user_id, now):
            continue

        delivery = get_local_delivery_slot(timezone_region, now)
        if delivery is None:
            continue

        local_date, slot = delivery

        entry = due_users.setdefault(
            user_id,
            {
                "local_date": local_date,
                "delivery_slot": slot,
                "timezone_region": timezone_region or "UTC",
                "subscriptions": [],
            },
        )

        entry["subscriptions"].append(subscription)

    return due_users


async def claim_delivery_slot(
    db,
    user_id: uuid.UUID,
    local_date: date,
    delivery_slot: int,
    message: dict,
    now: datetime,
) -> uuid.UUID | None:
    """
    Atomically claim one delivery slot.

    Failed and stale pending records can be retried.
    A sent record can never be claimed again.
    """

    new_id = uuid.uuid4()

    insert_stmt = (
        pg_insert(EngagementNotificationLog)
        .values(
            id=new_id,
            user_id=user_id,
            local_date=local_date,
            delivery_slot=delivery_slot,
            message_id=message["id"],
            category=message["category"],
            status="pending",
            attempts=1,
            sent_at=None,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(
            constraint="uq_engagement_log_user_date_slot"
        )
        .returning(EngagementNotificationLog.id)
    )

    inserted_id = (
        await db.execute(insert_stmt)
    ).scalar_one_or_none()

    await db.commit()

    if inserted_id is not None:
        return inserted_id

    stale_before = now - timedelta(minutes=STALE_PENDING_MINUTES)

    retry_condition = or_(
        EngagementNotificationLog.status == "failed",
        and_(
            EngagementNotificationLog.status == "pending",
            EngagementNotificationLog.updated_at < stale_before,
        ),
    )

    retry_stmt = (
        update(EngagementNotificationLog)
        .where(
            EngagementNotificationLog.user_id == user_id,
            EngagementNotificationLog.local_date == local_date,
            EngagementNotificationLog.delivery_slot == delivery_slot,
            EngagementNotificationLog.attempts < MAX_ATTEMPTS,
            retry_condition,
        )
        .values(
            status="pending",
            attempts=EngagementNotificationLog.attempts + 1,
            message_id=message["id"],
            category=message["category"],
            sent_at=None,
            last_error=None,
            updated_at=now,
        )
        .returning(EngagementNotificationLog.id)
    )

    claimed_id = (
        await db.execute(retry_stmt)
    ).scalar_one_or_none()

    await db.commit()
    return claimed_id


async def send_to_subscription(
    subscription: PushSubscription,
    payload: dict,
) -> tuple[bool, int | None, str | None]:
    """Send one Web Push notification without exposing subscription secrets."""

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
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_SUBJECT},
            ttl=300,
        )

        if 200 <= response.status_code < 300:
            return True, response.status_code, None

        return (
            False,
            response.status_code,
            f"Push service returned HTTP {response.status_code}",
        )

    except WebPushException as exc:
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)

        message = (
            f"Push service returned HTTP {status_code}"
            if status_code is not None
            else "Push request failed"
        )

        return False, status_code, message

    except Exception:
        logger.exception("Unexpected engagement push delivery error")
        return False, None, "Unexpected push delivery error"


async def process_user(
    db,
    user_id: uuid.UUID,
    entry: dict,
    now: datetime,
    dry_run: bool = False,
) -> tuple[bool, int]:
    """Recheck eligibility, claim a slot and deliver to all saved devices."""

    # Recheck rollout and consent immediately before processing.
    if not is_rollout_enabled(user_id, now):
        return False, 0

    result = await db.execute(
        select(User)
        .join(
            UserPreferences,
            UserPreferences.user_id == User.id,
        )
        .where(
            User.id == user_id,
            User.is_active.is_(True),
            User.is_suspended.is_(False),
            User.is_banned.is_(False),
            UserPreferences.engagement_notifications_enabled.is_(True),
        )
    )

    if result.scalar_one_or_none() is None:
        return False, 0

    # Recheck the local delivery window.
    delivery = get_local_delivery_slot(
        entry["timezone_region"],
        now,
    )

    if delivery != (entry["local_date"], entry["delivery_slot"]):
        return False, 0

    # Suppress users who are online or playing.
    if await is_user_online(user_id):
        logger.info("Skipping online user %s", user_id)
        return False, 0

    if await has_active_mystery(db, user_id, now):
        logger.info("Skipping user %s in an active mystery", user_id)
        return False, 0

    # Recheck subscriptions in case they were removed after collection.
    subscription_result = await db.execute(
        select(PushSubscription).where(
            PushSubscription.user_id == user_id
        )
    )
    subscriptions = list(subscription_result.scalars().all())

    if not subscriptions:
        return False, 0

    message = await select_message(db, user_id, now)
    if message is None:
        return False, 0

    if dry_run:
        logger.info(
            "Dry run: user=%s slot=%s date=%s message=%s devices=%d",
            user_id,
            entry["delivery_slot"],
            entry["local_date"],
            message["id"],
            len(subscriptions),
        )
        return False, 0

    log_id = await claim_delivery_slot(
        db=db,
        user_id=user_id,
        local_date=entry["local_date"],
        delivery_slot=entry["delivery_slot"],
        message=message,
        now=now,
    )

    if log_id is None:
        logger.info(
            "Skipping user %s: slot already sent, claimed or retry limit reached",
            user_id,
        )
        return False, 0

    # Final suppression check immediately before delivery.
    final_check_time = utcnow()
    suppression_reason = None
    if not is_rollout_enabled(user_id, final_check_time):
        suppression_reason = "Rollout disabled or expired"
    elif get_local_delivery_slot(
        entry["timezone_region"],
        final_check_time,
    ) != (entry["local_date"], entry["delivery_slot"]):
        suppression_reason = "Delivery window has closed"
    else:
        final_user_result = await db.execute(
            select(User.id)
            .join(
                UserPreferences,
                UserPreferences.user_id == User.id,
            )
            .where(
                User.id == user_id,
                User.is_active.is_(True),
                User.is_suspended.is_(False),
                User.is_banned.is_(False),
                UserPreferences.engagement_notifications_enabled.is_(True),
            )
        )
        if final_user_result.scalar_one_or_none() is None:
            suppression_reason = "User no longer eligible or has revoked consent"
    if suppression_reason is None:
        if await is_user_online(user_id):
            suppression_reason = "User became online"
        elif await has_active_mystery(db, user_id, final_check_time):
            suppression_reason = "User entered an active mystery"
    if suppression_reason is not None:
        await db.execute(
            delete(EngagementNotificationLog).where(
                EngagementNotificationLog.id == log_id,
                EngagementNotificationLog.status == "pending",
            )
        )
        await db.commit()
        logger.info(
            "Released engagement slot for user %s: %s",
            user_id,
            suppression_reason,
        )
        return False, 0

    payload = {
        "title": "Pairza",
        "body": message["body"],
        "url": message["url"],
        "tag": "pairza-engagement",
    }

    accepted_count = 0
    expired_ids = []
    errors = []

    for subscription in subscriptions:
        ok, status_code, error = await send_to_subscription(
            subscription,
            payload,
        )

        if ok:
            accepted_count += 1
        elif status_code in (404, 410):
            expired_ids.append(subscription.id)
        elif error:
            errors.append(error)

    if expired_ids:
        await db.execute(
            delete(PushSubscription).where(
                PushSubscription.id.in_(expired_ids)
            )
        )

    log = await db.get(EngagementNotificationLog, log_id)

    if log is not None:
        finished_at = utcnow()
        log.updated_at = finished_at

        if accepted_count:
            log.status = "sent"
            log.sent_at = finished_at
            log.last_error = None
        else:
            log.status = "failed"
            log.sent_at = None
            log.last_error = (
                "; ".join(errors)
                or "No push service accepted the notification"
            )[:500]

        await db.commit()

    return accepted_count > 0, len(expired_ids)


async def run(dry_run: bool = False) -> None:
    """Run one engagement notification pass."""

    settings = get_settings()

    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        raise RuntimeError("VAPID keys are not configured.")

    if not settings.VAPID_SUBJECT:
        raise RuntimeError("VAPID_SUBJECT is not configured.")

    now = utcnow()

    async with AsyncSessionLocal() as db:
        due_users = await collect_due_users(db, now)

        logger.info(
            "Engagement check at %s UTC: %d eligible user(s)",
            now.isoformat(),
            len(due_users),
        )

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
                    dry_run=dry_run,
                )

                expired_subscriptions += expired_count

                if sent:
                    sent_users += 1
                elif not dry_run:
                    skipped_or_failed += 1

            except Exception:
                await db.rollback()
                logger.exception(
                    "Failed to process engagement notification for user %s",
                    user_id,
                )
                skipped_or_failed += 1

        logger.info(
            "Engagement run finished: accepted=%d, "
            "skipped_or_failed=%d, expired_subscriptions_removed=%d, dry_run=%s",
            sent_users,
            skipped_or_failed,
            expired_subscriptions,
            dry_run,
        )
