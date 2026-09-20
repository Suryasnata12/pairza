from sqlalchemy import select

from app.mysteries import service as mysteries_service
from app.mysteries.models import MysteryCategoryConfig
from app.sessions.models import UserMysteryHistory
from tests.conftest import make_mystery, make_user


async def test_disabled_category_is_never_selected(db):
    await make_mystery(db, title="Enabled Mystery", category="geo")
    await make_mystery(db, title="Disabled Mystery", category="cipher")
    db.add(MysteryCategoryConfig(category="cipher", is_enabled=False))
    await db.commit()

    user_a = await make_user(db, "catdis_a@test.com", "catdis_a")
    user_b = await make_user(db, "catdis_b@test.com", "catdis_b")

    # Run selection many times — a disabled category must NEVER come up, not just usually.
    for _ in range(20):
        mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
        assert mystery is not None
        assert mystery.category != "cipher"


async def test_category_with_no_config_row_defaults_to_enabled(db):
    """Absence of a config row must mean enabled — adding a new category to
    the Python list should never silently break selection."""
    await make_mystery(db, title="No Config Mystery", category="pattern")
    user_a = await make_user(db, "noconf_a@test.com", "noconf_a")
    user_b = await make_user(db, "noconf_b@test.com", "noconf_b")

    mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
    assert mystery is not None
    assert mystery.category == "pattern"


async def test_all_categories_disabled_returns_none(db):
    await make_mystery(db, title="Only Mystery", category="geo")
    db.add(MysteryCategoryConfig(category="geo", is_enabled=False))
    await db.commit()

    user_a = await make_user(db, "alldis_a@test.com", "alldis_a")
    user_b = await make_user(db, "alldis_b@test.com", "alldis_b")

    mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
    assert mystery is None


async def test_selection_prefers_category_neither_player_just_had(db):
    from app.common.mixins import utcnow
    from tests.test_sessions import _create_session_directly

    geo_mystery = await make_mystery(db, title="Geo One", category="geo")
    logic_mystery = await make_mystery(db, title="Logic One", category="logic")

    user_a = await make_user(db, "div_a@test.com", "div_a")
    user_b = await make_user(db, "div_b@test.com", "div_b")

    # Both players' most recent mystery was "geo" — today's pick should lean toward "logic" instead.
    prior_session = await _create_session_directly(db, geo_mystery, user_a, user_b)
    for uid in (user_a.id, user_b.id):
        db.add(UserMysteryHistory(
            user_id=uid, mystery_id=geo_mystery.id, session_id=prior_session.id,
            category="geo", result="solved", solve_seconds=100, created_at=utcnow(),
        ))
    await db.commit()

    # Deterministic with only one non-recent category available — every run should pick "logic".
    for _ in range(10):
        mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
        assert mystery is not None
        assert mystery.category == "logic"


async def test_diversity_preference_falls_back_when_only_recent_category_available(db):
    """If the ONLY eligible mystery is in a category either player just had,
    selection must still succeed rather than returning nothing."""
    from app.common.mixins import utcnow
    from tests.test_sessions import _create_session_directly

    geo_mystery_1 = await make_mystery(db, title="Geo One", category="geo")
    geo_mystery_2 = await make_mystery(db, title="Geo Two", category="geo")

    user_a = await make_user(db, "fallback_a@test.com", "fallback_a")
    user_b = await make_user(db, "fallback_b@test.com", "fallback_b")

    prior_session = await _create_session_directly(db, geo_mystery_1, user_a, user_b)
    db.add(UserMysteryHistory(
        user_id=user_a.id, mystery_id=geo_mystery_1.id, session_id=prior_session.id,
        category="geo", result="solved", solve_seconds=100, created_at=utcnow(),
    ))
    await db.commit()

    # geo_mystery_1 is on cooldown (just played), but geo_mystery_2 (same
    # "recent" category) must still be selectable — falling back beats WAITING.
    mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, {geo_mystery_1.id})
    assert mystery is not None
    assert mystery.id == geo_mystery_2.id


async def test_mystery_with_no_defined_time_limit_is_never_selected(db):
    """A session's end time comes from the mystery's difficulty, so a row whose difficulty is outside
    the defined tiers (only possible via hand-edited data) must be skipped, not crash matchmaking."""
    await make_mystery(db, title="Bad Difficulty", category="geo", difficulty=9)
    user_a = await make_user(db, "baddiff_a@test.com", "baddiff_a")
    user_b = await make_user(db, "baddiff_b@test.com", "baddiff_b")

    assert await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set()) is None

    await make_mystery(db, title="Good Difficulty", category="cipher", difficulty=5)
    for _ in range(10):
        mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
        assert mystery is not None and mystery.title == "Good Difficulty"
