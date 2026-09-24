"""
Forgot password / forgot username, exercised through the real service layer against a real
database (not the synthetic harness used to design this feature — see git history/PR notes for
that). Pairza logs in by EMAIL (see auth/schemas.py's LoginRequest), so "forgot ID" here means
"I remember my username but not which email I used" — request_username_reminder is that path.

Both request_password_reset and request_username_reminder ALWAYS succeed from the caller's
point of view, whether or not the account exists — see their docstrings in auth/service.py for
why that's deliberate (email/username enumeration). reset_password is the one function that DOES
distinguish valid from invalid, because its input is a secret the caller must already have from
their inbox, not a guessable email or username.
"""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth import service as auth_service
from app.common.exceptions import UnauthorizedError
from app.common.mixins import utcnow
from app.users.models import PasswordResetToken, Profile, RefreshToken, User
from tests.conftest import make_user


async def _issue_refresh_token(db, user) -> RefreshToken:
    # Each call must get its own token_jti — refresh_tokens.token_jti is unique, and a real
    # user can easily have several live sessions (phone + laptop, say) at once.
    token = RefreshToken(
        user_id=user.id, token_jti=f"jti-{uuid.uuid4()}",
        expires_at=utcnow() + timedelta(days=30), created_at=utcnow(),
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token


# --- Forgot password ------------------------------------------------------------------------

async def test_request_reset_for_unknown_email_creates_no_token(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))

    await auth_service.request_password_reset(db, "nobody-at-all@test.com")

    assert sent == []
    rows = (await db.execute(select(PasswordResetToken))).scalars().all()
    assert rows == []


async def test_request_reset_for_real_account_creates_a_token_and_emails_a_link(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))
    user = await make_user(db, "resetme@test.com", "resetme")

    await auth_service.request_password_reset(db, "RESETME@test.com")  # case-insensitive

    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "resetme@test.com" and "reset" in subject.lower() and "reset-password?token=" in body

    tokens = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).scalars().all()
    assert len(tokens) == 1 and tokens[0].used_at is None


async def test_a_google_only_account_gets_no_reset_token(db, monkeypatch):
    """No password to reset — the request must do nothing, not error."""
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))
    user = await make_user(db, "googleuser@test.com", "googleuser")
    user.hashed_password = None
    user.google_sub = "some-google-sub"
    await db.commit()

    await auth_service.request_password_reset(db, "googleuser@test.com")

    assert sent == []
    rows = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).scalars().all()
    assert rows == []


async def test_requesting_again_invalidates_the_previous_token(db, monkeypatch):
    monkeypatch.setattr(auth_service, "send_email", lambda *a: None)
    user = await make_user(db, "tworequests@test.com", "tworequests")

    await auth_service.request_password_reset(db, "tworequests@test.com")
    first = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).scalar_one()

    await auth_service.request_password_reset(db, "tworequests@test.com")
    await db.refresh(first)
    all_tokens = (await db.execute(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))).scalars().all()

    assert first.used_at is not None  # the old one is dead
    assert len([t for t in all_tokens if t.used_at is None]) == 1  # only the newest works


# --- Reset password --------------------------------------------------------------------------

async def test_a_valid_token_changes_the_password_and_revokes_every_session(db, monkeypatch):
    monkeypatch.setattr(auth_service, "send_email", lambda *a: None)
    user = await make_user(db, "changeme@test.com", "changeme")
    rt1 = await _issue_refresh_token(db, user)
    rt2 = await _issue_refresh_token(db, user)

    captured = {}
    monkeypatch.setattr(auth_service, "send_email", lambda to, subject, body: captured.setdefault("link", body))
    await auth_service.request_password_reset(db, "changeme@test.com")
    raw_token = captured["link"].split("token=")[1].split("\n")[0].strip()

    await auth_service.reset_password(db, raw_token, "BrandNewPassword123!")

    refreshed_user = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    assert auth_service.verify_password("BrandNewPassword123!", refreshed_user.hashed_password)
    await db.refresh(rt1)
    await db.refresh(rt2)
    assert rt1.revoked is True and rt2.revoked is True


async def test_an_unknown_token_is_rejected(db):
    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.reset_password(db, "this-token-does-not-exist", "SomePassword123!")
    assert exc_info.value.code == "invalid_reset_token"


async def test_an_expired_token_is_rejected_and_password_is_untouched(db):
    user = await make_user(db, "expired@test.com", "expired")
    from app.auth.service import _hash_reset_token
    db.add(PasswordResetToken(
        user_id=user.id, token_hash=_hash_reset_token("expired-raw-token"),
        expires_at=utcnow() - timedelta(minutes=1), created_at=utcnow() - timedelta(minutes=31),
    ))
    await db.commit()
    original_hash = user.hashed_password

    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.reset_password(db, "expired-raw-token", "ShouldNotApply123!")
    assert exc_info.value.code == "invalid_reset_token"

    await db.refresh(user)
    assert user.hashed_password == original_hash


async def test_a_token_can_only_be_used_once(db, monkeypatch):
    monkeypatch.setattr(auth_service, "send_email", lambda *a: None)
    user = await make_user(db, "onceonly@test.com", "onceonly")
    captured = {}
    monkeypatch.setattr(auth_service, "send_email", lambda to, subject, body: captured.setdefault("link", body))
    await auth_service.request_password_reset(db, "onceonly@test.com")
    raw_token = captured["link"].split("token=")[1].split("\n")[0].strip()

    await auth_service.reset_password(db, raw_token, "First123!")

    with pytest.raises(UnauthorizedError) as exc_info:
        await auth_service.reset_password(db, raw_token, "Second123!")
    assert exc_info.value.code == "invalid_reset_token"

    await db.refresh(user)
    assert auth_service.verify_password("First123!", user.hashed_password)  # second attempt had no effect


# --- Forgot username -------------------------------------------------------------------------

async def test_forgot_username_emails_the_real_account_email(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))
    await make_user(db, "iforgot@test.com", "MyCoolUsername")

    await auth_service.request_username_reminder(db, "mycoolusername")  # case-insensitive

    assert len(sent) == 1
    to, subject, body = sent[0]
    assert to == "iforgot@test.com" and "iforgot@test.com" in body


async def test_forgot_username_for_unknown_username_sends_nothing(db, monkeypatch):
    sent = []
    monkeypatch.setattr(auth_service, "send_email", lambda *a: sent.append(a))

    await auth_service.request_username_reminder(db, "nobody_has_this_name")

    assert sent == []


async def test_forgot_username_never_leaks_the_email_in_the_return_value(db, monkeypatch):
    monkeypatch.setattr(auth_service, "send_email", lambda *a: None)
    await make_user(db, "hidden@test.com", "hiddenname")

    result = await auth_service.request_username_reminder(db, "hiddenname")

    assert result is None
