"""
Google sign-in: which account a verified Google identity may sign in to.

The headline case is ACCOUNT PRE-HIJACKING. Password sign-up never proves the person owns the
email, so an attacker can register someone else's address with a password of their own. If
Google sign-in then "matched by email", the real owner would land in the attacker's account,
with the attacker still holding its password and sessions. These tests pin the rule that stops
that: a Google identity is never linked to an account whose email ownership was never verified.

Google itself isn't contacted: the trust rule and the account decision are exercised directly,
and the endpoint tests swap `verify_google_id_token` for a stub that returns claims.
"""
import pytest
from fastapi import Response
from sqlalchemy import select

from app.auth import router as auth_router
from app.auth import service as auth_service
from app.auth.schemas import GoogleAuthRequest, RegisterRequest
from app.common.exceptions import ConflictError, UnauthorizedError
from app.users.models import Profile, User, UserPreferences
from tests.conftest import make_user

VICTIM_EMAIL = "victim@gmail.com"
ATTACKER_PASSWORD = "AttackerPass123!"


def google_claims(**overrides):
    claims = {"sub": "google-sub-victim", "email": VICTIM_EMAIL, "email_verified": True}
    claims.update(overrides)
    return claims


async def _attacker_preregisters(db) -> User:
    """Exactly what an attacker can do today: sign up with the victim's email. Unverified, holds a password."""
    return await auth_service.register_user(
        db, RegisterRequest(email=VICTIM_EMAIL, password=ATTACKER_PASSWORD, username="not_the_victim", country_code="US")
    )


# --- the trust rule: Google must vouch for the email --------------------------------------------

def test_a_verified_google_email_is_accepted():
    assert auth_service.extract_google_identity(google_claims()) == ("google-sub-victim", VICTIM_EMAIL)
    # Google sends a boolean; the string form some libraries produce is tolerated too.
    assert auth_service.extract_google_identity(google_claims(email_verified="true"))[1] == VICTIM_EMAIL


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "s", "email": "a@b.co", "email_verified": False},
        {"sub": "s", "email": "a@b.co", "email_verified": "false"},
        {"sub": "s", "email": "a@b.co"},                          # email_verified absent
        {"sub": "s", "email_verified": True},                      # no email at all (used to be a 500)
        {"sub": "s", "email": "   ", "email_verified": True},
        {"sub": "s", "email": None, "email_verified": True},
    ],
)
def test_an_unverified_or_missing_google_email_is_refused(claims):
    with pytest.raises(UnauthorizedError) as exc_info:
        auth_service.extract_google_identity(claims)
    assert exc_info.value.code == "google_email_unverified"


def test_a_token_without_a_subject_is_refused():
    with pytest.raises(UnauthorizedError):
        auth_service.extract_google_identity({"email": "a@b.co", "email_verified": True})


async def test_the_account_decision_re_checks_the_email_itself(db):
    """resolve_google_user must not rely on its caller having verified anything."""
    await make_user(db, VICTIM_EMAIL, "verified_user")
    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.resolve_google_user(db, google_claims(email_verified=False), None, None)
    assert exc_info.value.code == "google_email_unverified"


# --- THE ATTACK ----------------------------------------------------------------------------------

async def test_pre_registered_unverified_account_is_never_linked_to_a_google_login(db):
    attacker_account = await _attacker_preregisters(db)

    with pytest.raises(ConflictError) as exc_info:
        await auth_service.resolve_google_user(db, google_claims(), None, None)
    assert exc_info.value.code == "google_email_in_use"

    # Nothing about the attacker's account changed...
    await db.refresh(attacker_account)
    assert attacker_account.google_sub is None
    # ...it is still the attacker's, with their password...
    same = await auth_service.authenticate_user(db, VICTIM_EMAIL, ATTACKER_PASSWORD)
    assert same.id == attacker_account.id
    # ...and no second account was created for the victim's Google identity.
    rows = (await db.execute(select(User).where(User.email == VICTIM_EMAIL))).scalars().all()
    assert len(rows) == 1


async def test_the_refusal_holds_even_when_a_username_and_country_are_supplied(db):
    await _attacker_preregisters(db)
    with pytest.raises(ConflictError):
        await auth_service.resolve_google_user(db, google_claims(), "victim_name", "US")
    rows = (await db.execute(select(User).where(User.email == VICTIM_EMAIL))).scalars().all()
    assert len(rows) == 1


async def test_endpoint_refuses_the_attack_signs_nobody_in_and_sets_no_cookies(db, monkeypatch):
    attacker_account = await _attacker_preregisters(db)

    async def fake_verify(_id_token):
        return google_claims()

    monkeypatch.setattr(auth_service, "verify_google_id_token", fake_verify)

    response = Response()
    with pytest.raises(ConflictError) as exc_info:
        await auth_router.google_auth(GoogleAuthRequest(id_token="stub"), response, db)

    assert exc_info.value.code == "google_email_in_use"
    assert response.headers.getlist("set-cookie") == []  # no session for anyone
    await db.refresh(attacker_account)
    assert attacker_account.google_sub is None


# --- never re-point an account at a different Google identity -------------------------------------

async def test_a_different_google_identity_is_never_written_over_a_linked_account(db):
    original = await auth_service.resolve_google_user(db, google_claims(sub="google-sub-original"), "orig_user", "US")
    await db.commit()

    with pytest.raises(ConflictError) as exc_info:
        await auth_service.resolve_google_user(db, google_claims(sub="google-sub-imposter"), None, None)
    assert exc_info.value.code == "google_email_in_use"

    await db.refresh(original)
    assert original.google_sub == "google-sub-original"


# --- what must keep working ------------------------------------------------------------------------

async def test_a_new_email_creates_a_verified_google_only_account(db):
    user = await auth_service.resolve_google_user(db, google_claims(), "google_newcomer", "gb")
    await db.commit()

    assert user.google_sub == "google-sub-victim"
    assert user.is_verified is True          # legitimate now: Google's email_verified is enforced
    assert user.hashed_password is None      # Google-only: there is no password to steal or guess
    profile = (await db.execute(select(Profile).where(Profile.user_id == user.id))).scalar_one()
    assert (profile.username, profile.country_code) == ("google_newcomer", "GB")
    prefs = (await db.execute(select(UserPreferences).where(UserPreferences.user_id == user.id))).scalar_one_or_none()
    assert prefs is not None


async def test_first_time_google_signup_still_needs_a_username_and_country(db):
    for username, country in ((None, "US"), ("some_name", None), (None, None)):
        with pytest.raises(UnauthorizedError) as exc_info:
            await auth_service.resolve_google_user(db, google_claims(), username, country)
        assert exc_info.value.code == "google_needs_profile"
    assert (await db.execute(select(User).where(User.email == VICTIM_EMAIL))).scalar_one_or_none() is None


async def test_a_returning_google_user_signs_in_without_any_profile_fields(db):
    created = await auth_service.resolve_google_user(db, google_claims(), "returning_user", "US")
    await db.commit()

    again = await auth_service.resolve_google_user(db, google_claims(), None, None)
    assert again.id == created.id


async def test_a_verified_account_without_a_google_link_can_be_linked(db):
    """The forward-compatible path: once email verification exists, verified password accounts link safely."""
    verified = await make_user(db, VICTIM_EMAIL, "verified_owner")  # conftest users are verified and have a password

    linked = await auth_service.resolve_google_user(db, google_claims(), None, None)
    await db.commit()

    assert linked.id == verified.id
    await db.refresh(verified)
    assert verified.google_sub == "google-sub-victim"
    still = await auth_service.authenticate_user(db, VICTIM_EMAIL, "TestPassword123!")  # password login untouched
    assert still.id == verified.id


async def test_google_first_then_password_signup_with_the_same_email_is_rejected(db):
    google_user = await auth_service.resolve_google_user(db, google_claims(), "google_first", "US")
    await db.commit()

    with pytest.raises(ConflictError) as exc_info:
        await auth_service.register_user(
            db, RegisterRequest(email=VICTIM_EMAIL, password="SomePass123!", username="someone_else", country_code="US")
        )
    assert exc_info.value.code == "email_taken"
    with pytest.raises(UnauthorizedError):  # a Google-only account has no password to log in with
        await auth_service.authenticate_user(db, VICTIM_EMAIL, "SomePass123!")
    assert google_user.hashed_password is None


async def test_endpoint_creates_a_new_google_account_and_signs_it_in(db, monkeypatch):
    async def fake_verify(_id_token):
        return google_claims(sub="google-sub-fresh", email="fresh_person@gmail.com")

    monkeypatch.setattr(auth_service, "verify_google_id_token", fake_verify)

    response = Response()
    result = await auth_router.google_auth(
        GoogleAuthRequest(id_token="stub", username="fresh_person", country_code="us"), response, db
    )

    assert (result.email, result.username, result.is_verified) == ("fresh_person@gmail.com", "fresh_person", True)
    cookies = response.headers.getlist("set-cookie")
    assert len(cookies) == 2
    assert any(c.startswith("pairza_access_token=") for c in cookies)
    assert any(c.startswith("pairza_refresh_token=") for c in cookies)
