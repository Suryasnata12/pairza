from sqlalchemy import select

from app.users import router as users_router
from app.users.models import UserPreferences
from app.users.schemas import UpdatePreferencesRequest
from tests.conftest import make_user


async def test_engagement_notifications_default_to_disabled(db):
    user = await make_user(
        db,
        "engagement_default@test.com",
        "engagement_default",
    )

    result = await users_router.get_my_preferences(user, db)

    assert result.engagement_notifications_enabled is False


async def test_engagement_opt_in_and_opt_out(db):
    user = await make_user(
        db,
        "engagement_consent@test.com",
        "engagement_consent",
    )

    result = await db.execute(
        select(UserPreferences).where(
            UserPreferences.user_id == user.id
        )
    )
    prefs = result.scalar_one()

    assert prefs.engagement_notifications_enabled is False

    await users_router.update_preferences(
        UpdatePreferencesRequest(
            engagement_notifications_enabled=True
        ),
        user,
        db,
    )

    await db.refresh(prefs)

    assert prefs.engagement_notifications_enabled is True

    # Promotional consent must not change the other preference.
    assert prefs.notifications_enabled is True

    await users_router.update_preferences(
        UpdatePreferencesRequest(
            engagement_notifications_enabled=False
        ),
        user,
        db,
    )

    await db.refresh(prefs)

    assert prefs.engagement_notifications_enabled is False
    assert prefs.notifications_enabled is True