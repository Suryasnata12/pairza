import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.users import router as users_router
from app.users.models import UserPreferences
from app.users.schemas import UpdatePreferencesRequest
from tests.conftest import make_user


async def test_both_push_notification_preferences_default_to_disabled(db):
    user = await make_user(db, "push_default@test.com", "push_default")
    result = await users_router.get_my_preferences(user, db)

    assert result.notifications_enabled is False
    assert result.engagement_notifications_enabled is False


async def test_either_notification_preference_updates_both_categories(db):
    user = await make_user(db, "push_consent@test.com", "push_consent")
    result = await db.execute(
        select(UserPreferences).where(UserPreferences.user_id == user.id)
    )
    prefs = result.scalar_one()

    await users_router.update_preferences(
        UpdatePreferencesRequest(notifications_enabled=True), user, db
    )
    await db.refresh(prefs)
    assert prefs.notifications_enabled is True
    assert prefs.engagement_notifications_enabled is True

    await users_router.update_preferences(
        UpdatePreferencesRequest(engagement_notifications_enabled=False), user, db
    )
    await db.refresh(prefs)
    assert prefs.notifications_enabled is False
    assert prefs.engagement_notifications_enabled is False


async def test_contradictory_notification_preferences_are_rejected(db):
    user = await make_user(db, "push_conflict@test.com", "push_conflict")

    with pytest.raises(HTTPException) as exc_info:
        await users_router.update_preferences(
            UpdatePreferencesRequest(
                notifications_enabled=True,
                engagement_notifications_enabled=False,
            ),
            user,
            db,
        )

    assert exc_info.value.status_code == 422
