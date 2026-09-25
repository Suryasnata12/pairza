"""
Admin panel: displaying and filtering users by country.

`country_code` is required at registration for every real user (RegisterRequest.country_code),
so every profile has exactly one — this is a straightforward group-by/filter, not an estimate.
"""
from app.admin import service as admin_service
from tests.conftest import make_user


async def test_listing_users_includes_no_country_filter_by_default(db):
    a = await make_user(db, "nofilter_a@test.com", "nofilter_a", country_code="US")
    b = await make_user(db, "nofilter_b@test.com", "nofilter_b", country_code="FR")

    rows = await admin_service.list_users(db, search=None, limit=50, offset=0)

    ids = {r["user"].id for r in rows}
    assert {a.id, b.id} <= ids


async def test_country_filter_returns_only_matching_users(db):
    us_user = await make_user(db, "us_user@test.com", "us_user", country_code="US")
    fr_user = await make_user(db, "fr_user@test.com", "fr_user", country_code="FR")

    rows = await admin_service.list_users(db, search=None, limit=50, offset=0, country="US")

    ids = {r["user"].id for r in rows}
    assert us_user.id in ids
    assert fr_user.id not in ids
    assert all(r["profile"].country_code == "US" for r in rows)


async def test_country_filter_is_case_insensitive(db):
    user = await make_user(db, "case_test@test.com", "case_test", country_code="JP")

    rows = await admin_service.list_users(db, search=None, limit=50, offset=0, country="jp")

    assert user.id in {r["user"].id for r in rows}


async def test_country_filter_combines_with_search(db):
    await make_user(db, "combo_match@test.com", "combo_match_user", country_code="DE")
    await make_user(db, "combo_wrong_country@test.com", "combo_match_user2", country_code="IT")
    await make_user(db, "combo_wrong_name@test.com", "someone_else", country_code="DE")

    rows = await admin_service.list_users(db, search="combo_match", limit=50, offset=0, country="DE")

    usernames = {r["profile"].username for r in rows}
    assert usernames == {"combo_match_user"}


async def test_country_counts_reflect_how_many_users_joined_from_each(db):
    await make_user(db, "count_a@test.com", "count_a", country_code="US")
    await make_user(db, "count_b@test.com", "count_b", country_code="US")
    await make_user(db, "count_c@test.com", "count_c", country_code="FR")

    counts = {row["country_code"]: row["user_count"] for row in await admin_service.get_user_counts_by_country(db)}

    assert counts["US"] >= 2
    assert counts["FR"] >= 1


async def test_country_counts_are_ordered_most_users_first(db):
    for i in range(3):
        await make_user(db, f"order_a_{i}@test.com", f"order_a_{i}", country_code="BR")
    await make_user(db, "order_b@test.com", "order_b", country_code="EG")

    counts = await admin_service.get_user_counts_by_country(db)
    by_code = {row["country_code"]: row["user_count"] for row in counts}

    assert by_code["BR"] > by_code["EG"]
    # the list as a whole is sorted descending by count, not just these two entries
    values = [row["user_count"] for row in counts]
    assert values == sorted(values, reverse=True)


async def test_country_counts_never_double_counts_a_country_across_two_rows(db):
    await make_user(db, "dup_a@test.com", "dup_a", country_code="CA")
    await make_user(db, "dup_b@test.com", "dup_b", country_code="CA")

    counts = await admin_service.get_user_counts_by_country(db)
    codes = [row["country_code"] for row in counts]

    assert codes.count("CA") == 1
