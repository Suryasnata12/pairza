"""
Explicit, one-time production admin bootstrap.

Run with:
    ADMIN_EMAIL=you@yourcompany.com ADMIN_PASSWORD='...' python -m scripts.create_admin

This is the ONLY sanctioned way to get an admin account onto a production
database. It deliberately does NOT read Settings.ADMIN_USER_EMAIL /
ADMIN_USER_PASSWORD — those defaults exist solely for scripts/seed_demo.py's
guarded, development-only convenience and must never be treated as a real
credential. This script requires ADMIN_EMAIL and ADMIN_PASSWORD as
environment variables with NO default, so there is no predictable admin
credential a production deployment could accidentally inherit.

Safety properties:
  - Refuses to run if either environment variable is missing.
  - Refuses a password under 12 characters (a floor, not a full policy —
    reuses no external dependency, just a sanity check on obvious mistakes).
  - Never logs or prints the password, at any verbosity, on any path.
  - Idempotent by email: an existing account is promoted to admin in place
    (its password is untouched) rather than creating a duplicate; running
    this twice with the same email is safe.
  - Every promotion is printed to stdout as an audit trail (email + outcome
    only), so a deploy log shows exactly when and to whom admin access was
    granted, without ever showing how.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.common.database import AsyncSessionLocal
from app.common.security import hash_password
from app.users.models import Profile, User, UserPreferences

MIN_PASSWORD_LENGTH = 12


async def create_or_promote_admin(db, email: str, password: str, username: str) -> str:
    """Returns 'created' or 'promoted' — never returns or logs the password either way."""
    existing = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()

    if existing is not None:
        if existing.is_admin:
            return "already_admin"
        existing.is_admin = True
        await db.commit()
        return "promoted"

    user = User(email=email, hashed_password=hash_password(password), is_verified=True, is_admin=True)
    db.add(user)
    await db.flush()
    db.add(Profile(user_id=user.id, username=username, country_code="US"))
    db.add(UserPreferences(user_id=user.id))
    await db.commit()
    return "created"


async def main() -> None:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD")

    if not email or not password:
        print(
            "Refusing to run: both ADMIN_EMAIL and ADMIN_PASSWORD must be set as environment "
            "variables. There is no default — a production admin credential must never be "
            "predictable.\n"
            "Example: ADMIN_EMAIL=you@yourcompany.com ADMIN_PASSWORD='...' python -m scripts.create_admin",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Refusing to run: ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters.", file=sys.stderr)
        sys.exit(1)

    username = os.environ.get("ADMIN_USERNAME", "admin")

    async with AsyncSessionLocal() as db:
        outcome = await create_or_promote_admin(db, email, password, username)

    if outcome == "created":
        print(f"Created new admin account: {email}")
    elif outcome == "promoted":
        print(f"Promoted existing account to admin: {email}")
    else:
        print(f"{email} is already an admin — nothing to do.")


if __name__ == "__main__":
    asyncio.run(main())
