import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.common.email import send_email
from app.common.exceptions import ConflictError, UnauthorizedError, ValidationFailedError
from app.common.mixins import utcnow
from app.common.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.config.settings import get_settings
from app.users.models import PasswordResetToken, Profile, RefreshToken, User, UserPreferences

settings = get_settings()


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    existing_email = await db.execute(select(User).where(User.email == payload.email))
    if existing_email.scalar_one_or_none():
        raise ConflictError("An account with that email already exists.", code="email_taken")

    existing_username = await db.execute(select(Profile).where(Profile.username == payload.username))
    if existing_username.scalar_one_or_none():
        raise ConflictError("That username is already taken.", code="username_taken")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        is_verified=False,
    )
    db.add(user)
    await db.flush()  # get user.id without committing

    db.add(Profile(user_id=user.id, username=payload.username, country_code=payload.country_code))
    db.add(UserPreferences(user_id=user.id))

    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Constant-shape error whether the email doesn't exist or the password is
    # wrong, so login can't be used to enumerate registered accounts.
    if user is None or user.hashed_password is None or not verify_password(password, user.hashed_password):
        raise UnauthorizedError("That email and password don't match.", code="invalid_credentials")

    if user.is_banned:
        raise UnauthorizedError("This account has been suspended.", code="account_banned")

    return user


async def issue_token_pair(db: AsyncSession, user: User) -> tuple[str, str]:
    access_token = create_access_token(user.id, is_admin=user.is_admin)
    refresh_token, jti, expires_at = create_refresh_token(user.id)

    db.add(
        RefreshToken(
            user_id=user.id,
            token_jti=jti,
            expires_at=expires_at,
            created_at=utcnow(),
        )
    )
    await db.commit()
    return access_token, refresh_token


async def rotate_refresh_token(db: AsyncSession, raw_refresh_token: str) -> tuple[str, str]:
    from app.common.security import decode_token, TokenType

    payload = decode_token(raw_refresh_token)
    if not payload or payload.get("type") != TokenType.REFRESH.value:
        raise UnauthorizedError("Your session expired. Please sign in again.")

    jti = payload.get("jti")
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == jti))
    stored = result.scalar_one_or_none()

    if stored is None or stored.revoked or stored.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise UnauthorizedError("Your session expired. Please sign in again.")

    stored.revoked = True  # rotation: a refresh token is single-use

    user_result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_banned:
        raise UnauthorizedError("This account is no longer active.")

    access_token = create_access_token(user.id, is_admin=user.is_admin)
    new_refresh_token, new_jti, new_expires_at = create_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token_jti=new_jti, expires_at=new_expires_at, created_at=utcnow()))
    await db.commit()
    return access_token, new_refresh_token


async def revoke_refresh_token(db: AsyncSession, raw_refresh_token: str) -> None:
    from app.common.security import decode_token

    payload = decode_token(raw_refresh_token)
    if not payload:
        return
    result = await db.execute(select(RefreshToken).where(RefreshToken.token_jti == payload.get("jti")))
    stored = result.scalar_one_or_none()
    if stored:
        stored.revoked = True
        await db.commit()


GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUER = {"accounts.google.com", "https://accounts.google.com"}


def extract_google_identity(claims: dict) -> tuple[str, str]:
    """
    Returns (google_sub, email), but only for an identity Google itself vouches for.

    An ID token's `email` is only proof of mailbox ownership when `email_verified`
    is true. Everything downstream (creating an account and, above all, deciding
    whether a Google login is the same person as an existing account) rests on
    that, so a missing or unverified email is refused outright, never trusted.

    Used by BOTH verify_google_id_token and resolve_google_user, so the rule
    lives in one place and can't be bypassed by a future caller that hands
    resolve_google_user claims of its own.
    """
    google_sub = claims.get("sub")
    if not isinstance(google_sub, str) or not google_sub:
        raise UnauthorizedError("We couldn't verify that Google sign-in.")

    email = claims.get("email")
    flag = claims.get("email_verified")
    # Google sends a JSON boolean; tolerate the string "true" that some libraries/older tokens produce.
    email_verified = flag is True or (isinstance(flag, str) and flag.strip().lower() == "true")
    if not isinstance(email, str) or not email.strip() or not email_verified:
        raise UnauthorizedError(
            "Google hasn't verified the email on that account, so we can't sign you in with it.",
            code="google_email_unverified",
        )
    return google_sub, email


async def resolve_google_user(
    db: AsyncSession, claims: dict, username: str | None, country_code: str | None
) -> User:
    """
    Decides which Pairza account a verified Google identity signs in to.

      1. Already linked (google_sub matches)  -> sign in.
      2. No account with that email           -> create one (needs username + country).
      3. An account with that email exists    -> link ONLY if it is verified and not linked
         to some other Google identity. Otherwise refuse with 409 and change nothing.

    Why (3) never links to an unverified account: password sign-up does not prove
    the person owns the email. Anyone can register someone else's address with a
    password of their own; if Google then "matched by email" they would hand the
    real owner an account the attacker still holds the password and sessions for
    (account pre-hijacking). Linking a Google identity to an existing account
    needs proof of ownership of BOTH sides, and today only Google's side is proven.
    """
    google_sub, email = extract_google_identity(claims)

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        if existing.google_sub is not None:
            # Never silently re-point an account at a different Google identity.
            raise ConflictError(
                "That email is already connected to a different Google account.", code="google_email_in_use"
            )
        if not existing.is_verified:
            raise ConflictError(
                "An account with that email already exists. Sign in with your password instead.",
                code="google_email_in_use",
            )
        existing.google_sub = google_sub
        return existing

    if not username or not country_code:
        raise UnauthorizedError(
            "First-time Google sign-in needs a username and country.", code="google_needs_profile"
        )

    user = User(email=email, google_sub=google_sub, is_verified=True)  # verified: email_verified enforced above
    db.add(user)
    await db.flush()
    db.add(Profile(user_id=user.id, username=username, country_code=country_code.upper()))
    db.add(UserPreferences(user_id=user.id))
    return user


async def verify_google_id_token(id_token: str) -> dict:
    """
    Verifies a Google-issued ID token against Google's published JWKS, and that
    it carries a verified email (see extract_google_identity).

    Requires GOOGLE_CLIENT_ID to be configured — without it we can't check
    the `aud` claim, so we refuse rather than silently skip a security
    check. This call reaches the public internet (Google's cert endpoint),
    which is expected to work in any normal deployment even though it is
    unreachable from this sandboxed build environment.
    """
    if not settings.GOOGLE_CLIENT_ID:
        raise ValidationFailedError(
            "Google sign-in isn't configured on this server yet.", code="google_oauth_not_configured"
        )

    from jose import jwt as jose_jwt

    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(GOOGLE_CERTS_URL)
        resp.raise_for_status()
        jwks = resp.json()

    try:
        claims = jose_jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=settings.GOOGLE_CLIENT_ID,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced as a clean auth error, not a stack trace
        raise UnauthorizedError("We couldn't verify that Google sign-in.") from exc

    if claims.get("iss") not in GOOGLE_ISSUER:
        raise UnauthorizedError("We couldn't verify that Google sign-in.")

    extract_google_identity(claims)  # refuses a missing / unverified email
    return claims


# --- Forgot password / forgot username -----------------------------------------------------
#
# Pairza logs in by EMAIL, not username (see LoginRequest), so "forgot ID" here means
# "I remember my username but not which email I used" — request_username_reminder is that
# path. Both this and request_password_reset share the same shape on purpose: they ALWAYS
# return successfully to the caller regardless of whether the email/username exists, and the
# router returns one identical, generic message either way (see auth/router.py). Only
# reset_password itself, given a token the caller must already possess from their inbox,
# distinguishes valid from invalid — knowing a random secret is not an enumeration risk the
# way knowing an email or username is.

_RESET_TOKEN_BYTES = 32  # secrets.token_urlsafe(32) -> a 43-character, ~256-bit token


def _hash_reset_token(raw_token: str) -> str:
    """SHA-256 of the raw token — see PasswordResetToken's docstring for why only the hash is stored."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def request_password_reset(db: AsyncSession, email: str) -> None:
    result = await db.execute(select(User).where(func.lower(User.email) == email.strip().lower()))
    user = result.scalar_one_or_none()

    # Silently do nothing for: no such account, a Google-only account (nothing to reset — see
    # User.hashed_password), or an inactive/banned one. The caller sees the same generic
    # response as a successful send either way.
    if user is None or user.hashed_password is None or not user.is_active or user.is_banned:
        return

    # Invalidate any earlier unused token for this user first, so only the newest link ever works.
    await db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=utcnow())
    )

    raw_token = secrets.token_urlsafe(_RESET_TOKEN_BYTES)
    db.add(PasswordResetToken(
        user_id=user.id,
        token_hash=_hash_reset_token(raw_token),
        expires_at=utcnow() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        created_at=utcnow(),
    ))
    await db.commit()

    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"
    send_email(
        user.email,
        "Reset your Pairza password",
        "Someone requested a password reset for this Pairza account.\n\n"
        f"Reset your password: {reset_link}\n\n"
        f"This link expires in {settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes and can only be used once.\n\n"
        "If you didn't request this, you can safely ignore this email — your password hasn't been changed.",
    )


async def reset_password(db: AsyncSession, raw_token: str, new_password: str) -> None:
    token_hash = _hash_reset_token(raw_token)
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()

    now = utcnow()
    if (
        reset_token is None
        or reset_token.used_at is not None
        or reset_token.expires_at.replace(tzinfo=timezone.utc) < now
    ):
        raise UnauthorizedError(
            "This reset link is invalid or has expired. Please request a new one.", code="invalid_reset_token"
        )

    user_result = await db.execute(select(User).where(User.id == reset_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_banned:
        raise UnauthorizedError("This account is no longer active.", code="invalid_reset_token")

    reset_token.used_at = now  # single-use, even on a correct token
    user.hashed_password = hash_password(new_password)

    # A password reset must end every existing session on this account — the whole point of
    # resetting is that someone other than the account owner may currently have access.
    await db.execute(
        update(RefreshToken).where(RefreshToken.user_id == user.id, RefreshToken.revoked.is_(False)).values(revoked=True)
    )
    await db.commit()


async def request_username_reminder(db: AsyncSession, username: str) -> None:
    result = await db.execute(
        select(User)
        .join(Profile, Profile.user_id == User.id)
        .where(func.lower(Profile.username) == username.strip().lower())
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.is_banned:
        return

    send_email(
        user.email,
        "Your Pairza account email",
        f'Someone asked for a reminder of which email is linked to the Pairza username "{username}".\n\n'
        f"This address — {user.email} — is the one to sign in with.\n\n"
        "If you didn't request this, you can safely ignore this email.",
    )

