from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def due_reminder_date(
    current_streak: int,
    last_active_date: date | datetime | None,
    timezone_region: str | None,
    now_utc: datetime,
) -> date | None:
    """Return the user's local reminder date if a streak reminder is due."""

    if current_streak <= 0 or last_active_date is None:
        return None

    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)

    try:
        user_timezone = ZoneInfo(timezone_region or "UTC")
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        user_timezone = timezone.utc

    local_now = now_utc.astimezone(user_timezone)

    # Only send during the local evening window.
    if not 20 <= local_now.hour <= 23:
        return None

    # last_active_date represents the calendar date stored for the last solve.
    last_day = (
        last_active_date.date()
        if isinstance(last_active_date, datetime)
        else last_active_date
    )

    # The user must have played yesterday, but not yet today.
    if last_day != local_now.date() - timedelta(days=1):
        return None

    return local_now.date()