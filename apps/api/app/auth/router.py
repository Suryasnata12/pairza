from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.schemas import AuthUserResponse, GoogleAuthRequest, LoginRequest, RegisterRequest
from app.common.database import get_db
from app.common.deps import enforce_rate_limit, get_current_user
from app.common.exceptions import UnauthorizedError
from app.config.settings import get_settings
from app.users.models import Profile, User, UserPreferences

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

ACCESS_COOKIE = "pairza_access_token"
REFRESH_COOKIE = "pairza_refresh_token"

COOKIE_KWARGS = dict(
    httponly=True,
    samesite="lax",
    secure=settings.ENVIRONMENT != "development",
    path="/",
)


def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    response.set_cookie(ACCESS_COOKIE, access_token, max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, **COOKIE_KWARGS)
    response.set_cookie(
        REFRESH_COOKIE, refresh_token, max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600, **COOKIE_KWARGS
    )


@router.post("/register", response_model=AuthUserResponse, status_code=201)
async def register(payload: RegisterRequest, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit("auth_register", request.client.host, settings.RATE_LIMIT_AUTH_ATTEMPTS_PER_MINUTE)
    user = await service.register_user(db, payload)
    access_token, refresh_token = await service.issue_token_pair(db, user)
    _set_auth_cookies(response, access_token, refresh_token)
    return AuthUserResponse(id=user.id, email=user.email, username=payload.username, is_verified=user.is_verified, is_admin=user.is_admin)


@router.post("/login", response_model=AuthUserResponse)
async def login(payload: LoginRequest, response: Response, request: Request, db: AsyncSession = Depends(get_db)):
    await enforce_rate_limit("auth_login", request.client.host, settings.RATE_LIMIT_AUTH_ATTEMPTS_PER_MINUTE)
    user = await service.authenticate_user(db, payload.email, payload.password)
    access_token, refresh_token = await service.issue_token_pair(db, user)
    _set_auth_cookies(response, access_token, refresh_token)

    profile_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = profile_result.scalar_one()
    return AuthUserResponse(id=user.id, email=user.email, username=profile.username, is_verified=user.is_verified, is_admin=user.is_admin)


@router.post("/google", response_model=AuthUserResponse)
async def google_auth(payload: GoogleAuthRequest, response: Response, db: AsyncSession = Depends(get_db)):
    claims = await service.verify_google_id_token(payload.id_token)
    google_sub = claims["sub"]
    email = claims.get("email")

    result = await db.execute(select(User).where(User.google_sub == google_sub))
    user = result.scalar_one_or_none()

    if user is None:
        # First time we've seen this Google account — link by email if an
        # account already exists, otherwise provision a new one.
        existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            existing.google_sub = google_sub
            user = existing
        else:
            if not payload.username or not payload.country_code:
                raise UnauthorizedError(
                    "First-time Google sign-in needs a username and country.", code="google_needs_profile"
                )
            user = User(email=email, google_sub=google_sub, is_verified=True)
            db.add(user)
            await db.flush()
            db.add(Profile(user_id=user.id, username=payload.username, country_code=payload.country_code.upper()))
            db.add(UserPreferences(user_id=user.id))

    access_token, refresh_token = await service.issue_token_pair(db, user)
    _set_auth_cookies(response, access_token, refresh_token)

    profile_result = await db.execute(select(Profile).where(Profile.user_id == user.id))
    profile = profile_result.scalar_one()
    return AuthUserResponse(id=user.id, email=user.email, username=profile.username, is_verified=user.is_verified, is_admin=user.is_admin)


@router.post("/refresh")
async def refresh(response: Response, db: AsyncSession = Depends(get_db), refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)):
    if not refresh_token:
        raise UnauthorizedError("Your session expired. Please sign in again.")
    access_token, new_refresh_token = await service.rotate_refresh_token(db, refresh_token)
    _set_auth_cookies(response, access_token, new_refresh_token)
    return {"status": "refreshed"}


@router.post("/logout")
async def logout(response: Response, db: AsyncSession = Depends(get_db), refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE)):
    if refresh_token:
        await service.revoke_refresh_token(db, refresh_token)
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"status": "logged_out"}


@router.delete("/account")
async def delete_account(response: Response, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Per spec section 9: users can delete their account outright."""
    user.is_active = False
    user.email = f"deleted-{user.id}@pairza.invalid"
    await db.commit()
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"status": "account_deleted"}


@router.post("/ws-ticket")
async def issue_ws_ticket(user: User = Depends(get_current_user)):
    """
    The access token cookie is httpOnly by design, so browser JS can't read
    it to hand to `new WebSocket(url)` (which has no header/cookie API of
    its own for cross-origin use). Instead: mint a random, single-use,
    short-lived ticket over this authenticated REST call (the httpOnly
    cookie rides along automatically), and the client passes THAT in the
    WS URL's query string instead of ever exposing the real access token.
    """
    import secrets as _secrets

    from app.common.redis_client import get_redis

    ticket = _secrets.token_urlsafe(32)
    redis = get_redis()
    await redis.set(f"pairza:ws_ticket:{ticket}", str(user.id), ex=30)
    return {"ticket": ticket}
