"""
The security-hardening pass: proxy-aware rate limiting config, the JWT-secret startup guard,
requiring auth on the public profile endpoint (and hiding banned/deactivated accounts through
it), and case-insensitive email/username handling.

Docker network binding (Postgres/Redis to 127.0.0.1) has no Python-level behavior to test —
verify it with `docker compose ps` / `netstat` after deploying, not here.
"""
import inspect

import pytest
from sqlalchemy import select

from app.auth import service as auth_service
from app.auth.schemas import RegisterRequest
from app.common.deps import get_current_user
from app.common.exceptions import ConflictError, NotFoundError, UnauthorizedError
from app.config.settings import get_settings
from app.users import router as users_router
from app.users.models import User
from tests.conftest import make_user

settings = get_settings()


# --- JWT secret startup guard --------------------------------------------------------------

def test_default_jwt_secret_is_rejected_outside_development(monkeypatch):
    from app.main import DEFAULT_JWT_SECRET, _reject_insecure_startup_config

    monkeypatch.setattr(settings, "JWT_SECRET", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError):
        _reject_insecure_startup_config()


def test_default_jwt_secret_is_allowed_in_development(monkeypatch):
    from app.main import DEFAULT_JWT_SECRET, _reject_insecure_startup_config

    monkeypatch.setattr(settings, "JWT_SECRET", DEFAULT_JWT_SECRET)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    _reject_insecure_startup_config()  # must not raise


def test_a_real_jwt_secret_is_always_allowed(monkeypatch):
    from app.main import _reject_insecure_startup_config

    monkeypatch.setattr(settings, "JWT_SECRET", "a-real-randomly-generated-secret")
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    _reject_insecure_startup_config()  # must not raise


# --- Trusted proxy IPs default ---------------------------------------------------------------

def test_trusted_proxy_ips_defaults_to_empty_string():
    """Empty means 'trust nothing' — request.client.host is never overridden from a header
    unless this is explicitly configured. A plain `docker compose up` must be unaffected."""
    from app.config.settings import Settings

    assert Settings().TRUSTED_PROXY_IPS == ""


# --- Public profile endpoint now requires authentication --------------------------------------

def test_get_public_profile_requires_authentication_in_its_signature():
    """Structural check that Depends(get_current_user) is actually wired in — not just that the
    function happens to behave correctly when called directly (see the functional tests below)."""
    sig = inspect.signature(users_router.get_public_profile)
    current_user_param = sig.parameters["current_user"]
    assert current_user_param.default.dependency is get_current_user


async def test_get_public_profile_returns_a_real_active_users_profile(db):
    viewer = await make_user(db, "viewer@test.com", "viewer")
    target = await make_user(db, "target@test.com", "target_user")

    result = await users_router.get_public_profile(target.id, current_user=viewer, db=db)

    assert result.username == "target_user"


async def test_get_public_profile_404s_for_a_banned_account(db):
    viewer = await make_user(db, "viewer2@test.com", "viewer2")
    banned = await make_user(db, "banned@test.com", "banned_user")
    banned.is_banned = True
    await db.commit()

    with pytest.raises(NotFoundError):
        await users_router.get_public_profile(banned.id, current_user=viewer, db=db)


async def test_get_public_profile_404s_for_a_deactivated_account(db):
    viewer = await make_user(db, "viewer3@test.com", "viewer3")
    deactivated = await make_user(db, "deactivated@test.com", "deactivated_user")
    deactivated.is_active = False
    await db.commit()

    with pytest.raises(NotFoundError):
        await users_router.get_public_profile(deactivated.id, current_user=viewer, db=db)


async def test_get_public_profile_404s_for_an_unknown_user_id(db):
    import uuid

    viewer = await make_user(db, "viewer4@test.com", "viewer4")
    with pytest.raises(NotFoundError):
        await users_router.get_public_profile(uuid.uuid4(), current_user=viewer, db=db)


# --- Case-insensitive email and username -------------------------------------------------------

async def test_email_is_stored_lowercase_regardless_of_how_it_was_typed(db):
    payload = RegisterRequest(email="MixedCase@Test.com", password="SecurePass123!", username="mixed_case_user", country_code="US")
    user = await auth_service.register_user(db, payload)
    assert user.email == "mixedcase@test.com"


async def test_registering_the_same_email_in_a_different_case_is_rejected(db):
    await auth_service.register_user(
        db, RegisterRequest(email="dupe_case@test.com", password="SecurePass123!", username="dupe_case_one", country_code="US")
    )
    with pytest.raises(ConflictError) as exc_info:
        await auth_service.register_user(
            db, RegisterRequest(email="DUPE_CASE@TEST.COM", password="AnotherPass123!", username="dupe_case_two", country_code="US")
        )
    assert exc_info.value.code == "email_taken"


async def test_registering_the_same_username_in_a_different_case_is_rejected(db):
    await auth_service.register_user(
        db, RegisterRequest(email="uname_a@test.com", password="SecurePass123!", username="CoolName", country_code="US")
    )
    with pytest.raises(ConflictError) as exc_info:
        await auth_service.register_user(
            db, RegisterRequest(email="uname_b@test.com", password="SecurePass123!", username="coolname", country_code="US")
        )
    assert exc_info.value.code == "username_taken"


async def test_username_display_casing_is_preserved_even_though_matching_is_case_insensitive(db):
    """The uniqueness check is case-insensitive; what's actually stored and shown is not lowercased."""
    user = await auth_service.register_user(
        db, RegisterRequest(email="display_case@test.com", password="SecurePass123!", username="CoolName", country_code="US")
    )
    from app.users.models import Profile

    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    assert profile.username == "CoolName"


async def test_login_succeeds_regardless_of_email_casing(db):
    await auth_service.register_user(
        db, RegisterRequest(email="caselogin@test.com", password="CorrectPass123!", username="caselogin_user", country_code="US")
    )

    for attempt in ("caselogin@test.com", "CaseLogin@Test.com", "CASELOGIN@TEST.COM"):
        user = await auth_service.authenticate_user(db, attempt, "CorrectPass123!")
        assert user.email == "caselogin@test.com"


async def test_login_with_wrong_password_still_fails_regardless_of_email_casing(db):
    await auth_service.register_user(
        db, RegisterRequest(email="casewrong@test.com", password="CorrectPass123!", username="casewrong_user", country_code="US")
    )
    with pytest.raises(UnauthorizedError):
        await auth_service.authenticate_user(db, "CaseWrong@Test.com", "WrongPassword")
