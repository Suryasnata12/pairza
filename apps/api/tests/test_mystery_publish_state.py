"""
`is_published` (the gate matchmaking reads) and `status` (the lifecycle field
the admin panel and AI generator read) must always move together. These tests
pin that down for every code path that can flip publish state.
"""
from app.admin import service as admin_service
from app.mysteries.schemas import MysteryUpdate
from tests.conftest import make_mystery


async def test_publish_sets_status_published(db):
    mystery = await make_mystery(db, title="Draft One", is_published=False)
    assert mystery.status == "DRAFT"

    result = await admin_service.set_publish_state(db, mystery.id, True)

    assert result.is_published is True
    assert result.status == "PUBLISHED"


async def test_publish_promotes_validated_mystery(db):
    """AI-generated mysteries wait at VALIDATED when MYSTERY_AUTO_PUBLISH=false;
    an admin publishing one must move it all the way to PUBLISHED."""
    mystery = await make_mystery(db, title="Validated One", is_published=False)
    mystery.status = "VALIDATED"
    await db.commit()

    result = await admin_service.set_publish_state(db, mystery.id, True)

    assert result.is_published is True
    assert result.status == "PUBLISHED"


async def test_unpublish_moves_published_to_disabled(db):
    mystery = await make_mystery(db, title="Live One", is_published=True)
    assert mystery.status == "PUBLISHED"

    result = await admin_service.set_publish_state(db, mystery.id, False)

    assert result.is_published is False
    assert result.status == "DISABLED"


async def test_unpublish_leaves_never_live_status_alone(db):
    mystery = await make_mystery(db, title="Never Live", is_published=False)
    mystery.status = "VALIDATED"
    await db.commit()

    result = await admin_service.set_publish_state(db, mystery.id, False)

    assert result.is_published is False
    assert result.status == "VALIDATED"


async def test_patch_is_published_keeps_status_in_sync(db):
    """PATCH /admin/mysteries/{id} accepts is_published too — it must not
    bypass the lifecycle field."""
    mystery = await make_mystery(db, title="Patched One", is_published=False)

    published = await admin_service.update_mystery(db, mystery.id, MysteryUpdate(is_published=True))
    assert (published.is_published, published.status) == (True, "PUBLISHED")

    unpublished = await admin_service.update_mystery(db, mystery.id, MysteryUpdate(is_published=False))
    assert (unpublished.is_published, unpublished.status) == (False, "DISABLED")


async def test_category_pool_counts_follow_publish_state(db):
    await make_mystery(db, title="Live Geo", category="geo", is_published=True)
    await make_mystery(db, title="Draft Geo", category="geo", is_published=False)

    configs = {c["category"]: c for c in await admin_service.list_category_configs(db)}

    assert configs["geo"]["published_count"] == 1
    assert configs["geo"]["draft_count"] == 1
