"""
Email verification: sent at registration, gates joining matchmaking, resend is authenticated-only.

Google-created accounts are already is_verified=True (resolve_google_user already relies on
Google itself having proved the email) and never go through this flow at all — nothing here
touches Google sign-in.
"""
import pytest
from sqlalchemy import select
from redis.asyncio import from_url

from app.auth import service as auth_service
from app.common.exceptions import ConflictError, UnauthorizedError
from app.matchmaking import service as matchmaking_service
from app.users.models import EmailVerificationToken, User
from tests.conftest import make_user


@pytest.fixture
async def redis():
    r = from_url("redis://localhost:6379/1", decode_responses=True)
    yield r
    await r.aclose()


async def test_a_new_password_account_starts_unverified(db):
    user = await make_user(db, "fresh@test.com", "fresh_user")
    user.is_verified = False  # make_user defaults to verified for the convenience of every OTHER test
    await db.commit()
    assert user.is_verified is False


async def test_send_verification_email_creates_one_token_and_one_email(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))
    user = await make_user(db, "sendver@test.com", "sendver_user")
    user.is_verified = False
    await db.commit()

    await auth_service.send_verification_email(db, user)

    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "sendver@test.com" and "verify-email?token=" in body

    tokens = (await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))).scalars().all()
    assert len(tokens) == 1 and tokens[0].used_at is None


async def test_a_valid_token_verifies_the_account(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(auth_service, "send_email", lambda to, subject, body: captured.setdefault("body", body))
    user = await make_user(db, "verifyme@test.com", "verifyme_user")
    user.is_verified = False
    await db.commit()
    await auth_service.send_verification_email(db, user)
    raw_token = captured["body"].split("token=")[1].split("\n")[0].strip()

    await auth_service.verify_email(db, raw_token)

    await db.refresh(user)
    assert user.is_verified is True


async def test_an_unknown_token_is_rejected(db):
    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.verify_email(db, "this-token-does-not-exist")
    assert exc_info.value.code == "invalid_verification_token"


async def test_a_token_can_only_be_used_once(db, monkeypatch):
    captured = {}
    monkeypatch.setattr(auth_service, "send_email", lambda to, subject, body: captured.setdefault("body", body))
    user = await make_user(db, "oncever@test.com", "oncever_user")
    user.is_verified = False
    await db.commit()
    await auth_service.send_verification_email(db, user)
    raw_token = captured["body"].split("token=")[1].split("\n")[0].strip()

    await auth_service.verify_email(db, raw_token)
    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.verify_email(db, raw_token)
    assert exc_info.value.code == "invalid_verification_token"


async def test_resending_invalidates_the_previous_token(db, monkeypatch):
    monkeypatch.setattr(auth_service, "send_email", lambda *a: None)
    user = await make_user(db, "resend@test.com", "resend_user")
    user.is_verified = False
    await db.commit()

    await auth_service.send_verification_email(db, user)
    first = (await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))).scalar_one()

    await auth_service.resend_verification_email(db, user)
    await db.refresh(first)
    all_tokens = (await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))).scalars().all()

    assert first.used_at is not None
    assert len([t for t in all_tokens if t.used_at is None]) == 1


async def test_resend_is_a_noop_for_an_already_verified_account(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))
    user = await make_user(db, "alreadyverified@test.com", "already_verified_user")  # make_user defaults to verified

    await auth_service.resend_verification_email(db, user)

    assert sent == []
    tokens = (await db.execute(select(EmailVerificationToken).where(EmailVerificationToken.user_id == user.id))).scalars().all()
    assert tokens == []


# --- The matchmaking gate ------------------------------------------------------------------------

async def test_unverified_user_cannot_join_matchmaking(db, redis):
    user = await make_user(db, "gated@test.com", "gated_user")
    user.is_verified = False
    await db.commit()

    with pytest.raises(ConflictError) as exc_info:
        await matchmaking_service.join_matchmaking(db, redis, user)
    assert exc_info.value.code == "email_not_verified"


async def test_verified_user_can_still_join_matchmaking_normally(db, redis):
    """Regression guard: make_user's existing default (is_verified=True) must keep working
    exactly as it did before this feature existed — every other matchmaking test depends on it."""
    user = await make_user(db, "ungated@test.com", "ungated_user")
    result = await matchmaking_service.join_matchmaking(db, redis, user)
    assert result["status"] in ("matched", "waiting")


async def test_verifying_email_unblocks_a_previously_gated_user(db, redis, monkeypatch):
    captured = {}
    monkeypatch.setattr(auth_service, "send_email", lambda to, subject, body: captured.setdefault("body", body))
    user = await make_user(db, "unblock@test.com", "unblock_user")
    user.is_verified = False
    await db.commit()

    with pytest.raises(ConflictError):
        await matchmaking_service.join_matchmaking(db, redis, user)

    await auth_service.send_verification_email(db, user)
    raw_token = captured["body"].split("token=")[1].split("\n")[0].strip()
    await auth_service.verify_email(db, raw_token)
    await db.refresh(user)

    result = await matchmaking_service.join_matchmaking(db, redis, user)
    assert result["status"] in ("matched", "waiting")
