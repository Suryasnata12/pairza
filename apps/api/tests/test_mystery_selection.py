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


# --- Adaptive difficulty ------------------------------------------------------------------------

async def test_target_difficulty_prefers_an_exact_match_when_one_exists(db):
    """A no-surprise roll (rng always returns 1.0, so no SurpriseRule ever fires) at rank 2+2
    must land on the difficulty-2 mystery, not the 1 or 3 that are also on offer."""
    import random
    await make_mystery(db, title="Too Easy", category="geo", difficulty=1)
    await make_mystery(db, title="Just Right", category="cipher", difficulty=2)
    await make_mystery(db, title="Too Hard", category="logic", difficulty=3)
    user_a = await make_user(db, "tgt_a@test.com", "tgt_a")
    user_b = await make_user(db, "tgt_b@test.com", "tgt_b")

    never_surprise = random.Random()
    never_surprise.random = lambda: 1.0  # always fails every SurpriseRule's `< chance` check

    for _ in range(10):
        mystery = await mysteries_service.pick_random_mystery_for_pair(
            db, user_a.id, user_b.id, set(), rank_a=2, rank_b=2, rng=never_surprise,
        )
        assert mystery is not None and mystery.title == "Just Right"


async def test_a_rank_2_and_rank_4_pair_gets_the_rank_2_ceiling(db):
    """Rank 2 + Rank 4 -> base difficulty 2 (the lower-ranked player sets the ceiling),
    end to end through the actual selection function, not just the pure helper."""
    import random
    await make_mystery(db, title="Pair Ceiling Mystery", category="geo", difficulty=2)
    await make_mystery(db, title="Above Ceiling Mystery", category="cipher", difficulty=4)
    user_a = await make_user(db, "ceil_a@test.com", "ceil_a")
    user_b = await make_user(db, "ceil_b@test.com", "ceil_b")

    never_surprise = random.Random()
    never_surprise.random = lambda: 1.0

    for rank_a, rank_b in [(2, 4), (4, 2)]:  # order-independent
        mystery = await mysteries_service.pick_random_mystery_for_pair(
            db, user_a.id, user_b.id, set(), rank_a=rank_a, rank_b=rank_b, rng=never_surprise,
        )
        assert mystery is not None and mystery.title == "Pair Ceiling Mystery"


async def test_a_surprise_roll_can_select_above_the_pairs_base_ceiling(db):
    """Surprise challenge may exceed the base difficulty ceiling only when the surprise rule
    allows it — here it's forced to allow it (rng always returns 0.0, so the very first
    SurpriseRule always fires), and a rank-2+2 pair must be able to reach the level-4 mystery."""
    import random
    await make_mystery(db, title="Base Level Mystery", category="geo", difficulty=2)
    await make_mystery(db, title="Surprise Mystery", category="cipher", difficulty=3)
    user_a = await make_user(db, "sur_a@test.com", "sur_a")
    user_b = await make_user(db, "sur_b@test.com", "sur_b")

    always_surprise = random.Random()
    always_surprise.random = lambda: 0.0  # always wins the FIRST SurpriseRule (levels_up=1) -> target 3

    for _ in range(10):
        mystery = await mysteries_service.pick_random_mystery_for_pair(
            db, user_a.id, user_b.id, set(), rank_a=2, rank_b=2, rng=always_surprise,
        )
        assert mystery is not None and mystery.title == "Surprise Mystery"


async def test_surprise_above_every_available_difficulty_falls_back_to_the_hardest_available(db):
    """The pool has nothing at the surprise target — selection must fall back to the hardest
    mystery AT OR BELOW the target rather than either crashing or exceeding what was rolled."""
    import random
    await make_mystery(db, title="Only Easy Mystery", category="geo", difficulty=1)
    user_a = await make_user(db, "fb_a@test.com", "fb_a")
    user_b = await make_user(db, "fb_b@test.com", "fb_b")

    always_surprise = random.Random()
    always_surprise.random = lambda: 0.0

    mystery = await mysteries_service.pick_random_mystery_for_pair(
        db, user_a.id, user_b.id, set(), rank_a=1, rank_b=1, rng=always_surprise,
    )
    assert mystery is not None and mystery.title == "Only Easy Mystery"


async def test_default_ranks_still_work_for_callers_that_do_not_pass_any(db):
    """Backward compatibility: existing callers (and the pre-adaptive-difficulty tests above
    this one in this file) that never pass rank_a/rank_b or rng must keep working."""
    await make_mystery(db, title="No Rank Args Mystery", category="geo", difficulty=1)
    user_a = await make_user(db, "norank_a@test.com", "norank_a")
    user_b = await make_user(db, "norank_b@test.com", "norank_b")

    mystery = await mysteries_service.pick_random_mystery_for_pair(db, user_a.id, user_b.id, set())
    assert mystery is not None and mystery.title == "No Rank Args Mystery"
