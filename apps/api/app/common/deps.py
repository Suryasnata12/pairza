import uuid

from fastapi import Cookie, Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.database import get_db
from app.common.exceptions import ForbiddenError, RateLimitedError, UnauthorizedError
from app.common.redis_client import RedisKeys, get_redis
from app.common.security import TokenType, decode_token
from app.users.models import User


async def _extract_access_token(
    authorization: str | None = Header(default=None),
    access_token_cookie: str | None = Cookie(default=None, alias="pairza_access_token"),
) -> str:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1]
    if access_token_cookie:
        return access_token_cookie
    raise UnauthorizedError("You need to sign in to do that.")


async def get_current_user(
    token: str = Depends(_extract_access_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload or payload.get("type") != TokenType.ACCESS.value:
        raise UnauthorizedError("Your session isn't valid. Please sign in again.")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedError("This account is no longer active.")
    if user.is_banned:
        raise ForbiddenError("This account has been suspended.")

    return user


async def get_current_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise ForbiddenError("Admins only.")
    return user


async def get_optional_user(
    authorization: str | None = Header(default=None),
    access_token_cookie: str | None = Cookie(default=None, alias="pairza_access_token"),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]
    elif access_token_cookie:
        token = access_token_cookie
    if not token:
        return None
    payload = decode_token(token)
    if not payload or payload.get("type") != TokenType.ACCESS.value:
        return None
    result = await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))
    return result.scalar_one_or_none()


async def enforce_rate_limit(scope: str, identity: str, limit_per_minute: int) -> None:
    """Fixed-window limiter backed by Redis (spec section 43). Cheap, good enough for MVP scale."""
    redis = get_redis()
    key = RedisKeys.RATE_LIMIT.format(scope=scope, identity=identity)
    current = await redis.incr(key)
    if current == 1:
        await redis.expire(key, 60)
    if current > limit_per_minute:
        raise RateLimitedError("You're doing that a little too fast. Give it a moment.")
