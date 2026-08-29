"""
Auth primitives. Per spec section 9/43:
  - Argon2id for password hashing, never plaintext.
  - JWT access + refresh tokens, refresh tokens are rotated and stored
    hashed so a leaked DB dump doesn't hand out valid sessions.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from jose import JWTError, jwt

from app.config.settings import get_settings

settings = get_settings()

# argon2-cffi defaults already target argon2id with sane cost params;
# we set them explicitly so the choice is visible and tunable.
_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MB
    parallelism=2,
    hash_len=32,
    salt_len=16,
)


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(raw_password: str) -> str:
    return _hasher.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    try:
        return _hasher.verify(hashed_password, raw_password)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(hashed_password: str) -> bool:
    return _hasher.check_needs_rehash(hashed_password)


def create_access_token(user_id: uuid.UUID, is_admin: bool = False) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": TokenType.ACCESS.value,
        "is_admin": is_admin,
        "iat": now,
        "exp": now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> tuple[str, str, datetime]:
    """Returns (raw_token_for_client, opaque_id_to_store, expires_at).

    We embed a random jti so each refresh token is unique even if issued in
    the same second, and so it can be individually revoked/rotated.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    jti = secrets.token_urlsafe(32)
    payload = {
        "sub": str(user_id),
        "type": TokenType.REFRESH.value,
        "jti": jti,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, jti, expires_at


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
