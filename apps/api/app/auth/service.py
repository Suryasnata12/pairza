import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.common.exceptions import ConflictError, UnauthorizedError, ValidationFailedError
from app.common.mixins import utcnow
from app.common.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.config.settings import get_settings
from app.users.models import Profile, RefreshToken, User, UserPreferences

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


async def verify_google_id_token(id_token: str) -> dict:
    """
    Verifies a Google-issued ID token against Google's published JWKS.

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

    return claims
