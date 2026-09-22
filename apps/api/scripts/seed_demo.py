"""
DEVELOPMENT / DEMO ONLY — do not run this against a production database.

Run with: python -m scripts.seed_demo

Populates a rich fake environment for local development and demos: a stable
demo account, an admin account, ~24 fake users with fabricated profiles, and
several weeks of fabricated matches/sessions/history so the admin analytics
dashboard has something to show. NONE of this represents real user activity,
and every DAU/MAU/retention number it produces is fake.

Real production initialization is `python -m scripts.seed_system`, which
creates no users and no fake activity at all — see that script's own
docstring. This script explicitly refuses to run unless
ENVIRONMENT=development (see the guard in main(), below), as a safeguard
against running it against a real deployment by mistake. It does not replace
seed_system — run that first (this script also calls it, so mysteries and
badges exist for the fake activity to reference).

For creating a real admin account in production, use
`python -m scripts.create_admin` instead — it never fabricates a password
and never prints one.
"""
import asyncio
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from faker import Faker
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.common.database import AsyncSessionLocal
from app.common.mixins import utcnow
from app.common.security import hash_password
from app.config.settings import get_settings
from app.matchmaking.models import Match, MatchHistory
from app.mysteries.difficulty import time_limit_for_difficulty
from app.mysteries.models import Mystery, MysteryStage
from app.sessions.models import MysterySession, UserMysteryHistory
from app.users.models import Profile, User, UserDailyActivity, UserPreferences

from scripts.seed_system import main as seed_system_main

fake = Faker()
settings = get_settings()

COUNTRIES = [
    "US", "GB", "CA", "AU", "DE", "FR", "JP", "KR", "BR", "IN",
    "MX", "IT", "ES", "NL", "SE", "NO", "PL", "AR", "ZA", "NG",
    "EG", "TH", "VN", "PH", "TR", "PT", "IE", "NZ", "SG", "CH",
]
INTERESTS_POOL = [
    "true crime", "chess", "astronomy", "language learning", "cartography",
    "cryptography", "birdwatching", "film noir", "vintage synths", "urban exploring",
    "linguistics", "archaeology", "board games", "amateur radio", "cold cases",
]
EXPERIENCE_LEVELS = ["beginner", "intermediate", "advanced"]


async def seed_users(db, count: int = 24) -> list[User]:
    users = []
    # A stable, memorable demo account first.
    demo_email = settings.DEMO_USER_EMAIL
    existing = await db.execute(select(User).where(User.email == demo_email))
    if not existing.scalar_one_or_none():
        demo_user = User(email=demo_email, hashed_password=hash_password(settings.DEMO_USER_PASSWORD), is_verified=True)
        db.add(demo_user)
        await db.flush()
        db.add(Profile(user_id=demo_user.id, username="curious_fox", country_code="US", xp=250, mystery_count=2, solved_count=2, current_streak=2, longest_streak=2, countries_encountered=["GB"], categories_completed=["geo"]))
        db.add(UserPreferences(user_id=demo_user.id, timezone_region="America/New_York", interests=["true crime", "cartography"], puzzle_experience_level="intermediate"))
        users.append(demo_user)

    admin_email = settings.ADMIN_USER_EMAIL
    existing_admin = await db.execute(select(User).where(User.email == admin_email))
    if not existing_admin.scalar_one_or_none():
        admin_user = User(email=admin_email, hashed_password=hash_password(settings.ADMIN_USER_PASSWORD), is_verified=True, is_admin=True)
        db.add(admin_user)
        await db.flush()
        db.add(Profile(user_id=admin_user.id, username="pairza_hq", country_code="US"))
        db.add(UserPreferences(user_id=admin_user.id))
        users.append(admin_user)

    for i in range(count):
        email = f"seed_user_{i}@pairza.app"
        existing_u = await db.execute(select(User).where(User.email == email))
        if existing_u.scalar_one_or_none():
            continue
        u = User(email=email, hashed_password=hash_password(settings.SEED_USER_PASSWORD), is_verified=True)
        db.add(u)
        await db.flush()
        username = f"{fake.word()}_{fake.word()}{random.randint(1,99)}"[:32]
        db.add(Profile(
            user_id=u.id, username=username, country_code=random.choice(COUNTRIES),
            xp=random.randint(0, 4000), mystery_count=random.randint(0, 40),
        ))
        db.add(UserPreferences(
            user_id=u.id, timezone_region=fake.timezone(),
            interests=random.sample(INTERESTS_POOL, k=3),
            puzzle_experience_level=random.choice(EXPERIENCE_LEVELS),
        ))
        users.append(u)

    await db.commit()
    return users


async def seed_historical_engagement(db) -> None:
    """
    Backfills ~5-38 days of simulated daily activity, matches, and completed
    sessions so the admin analytics dashboard (DAU/MAU/retention/matches-
    per-user/etc.) has real numbers to show the first time anyone opens it,
    rather than every metric reading zero or "—" until real usage
    accumulates.

    Runs exactly once: if any UserDailyActivity row already exists, this is
    skipped entirely, since running it a second time would layer more fake
    history on top of by-then-real activity and quietly corrupt it.

    One side effect worth knowing about: this writes real MatchHistory and
    UserMysteryHistory rows, which the live matchmaking cooldowns (don't
    re-pair the same two people or re-serve the same mystery too soon) also
    read from. For a handful of seed accounts, this can very occasionally
    make an immediate rematch or a specific mystery briefly unavailable —
    harmless, and it resolves itself as the backdated cooldown window
    passes.
    """
    already_seeded = (await db.execute(select(func.count()).select_from(UserDailyActivity))).scalar_one()
    if already_seeded > 0:
        print("Historical engagement data already present — skipping backfill.")
        return

    user_ids = list(
        (await db.execute(select(User.id).join(Profile, Profile.user_id == User.id).where(User.is_admin.is_(False))))
        .scalars()
        .all()
    )
    mysteries = list(
        (await db.execute(select(Mystery).options(selectinload(Mystery.stages)).where(Mystery.is_published.is_(True))))
        .scalars()
        .all()
    )
    if not user_ids or not mysteries:
        print("No users or mysteries to backfill engagement history for — skipping.")
        return

    today = utcnow().date()
    activity_by_day: dict = {}

    for user_id in user_ids:
        join_offset = random.randint(3, 38)
        current_date = today - timedelta(days=join_offset)
        active = True
        while current_date <= today and active:
            db.add(UserDailyActivity(user_id=user_id, activity_date=current_date))
            activity_by_day.setdefault(current_date, []).append(user_id)
            # Rough retention decay: most people who show up keep coming
            # back for a few days, a chunk drop off, and a smaller loyal
            # core sticks around for weeks — enough shape for D1/D7/D30
            # retention to show real, varied percentages rather than 0 or 100.
            if random.random() > 0.72:
                active = False
            current_date += timedelta(days=1)

    await db.commit()

    for day, active_user_ids in activity_by_day.items():
        pool = active_user_ids.copy()
        random.shuffle(pool)
        for user_a_id, user_b_id in zip(pool[::2], pool[1::2]):
            if random.random() > 0.55:  # not every pair of co-active users starts a fresh match that exact day
                continue

            mystery = random.choice(mysteries)
            match_time = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
                hours=random.randint(6, 22), minutes=random.randint(0, 59)
            )

            match = Match(user_a_id=user_a_id, user_b_id=user_b_id, mystery_id=mystery.id, created_at=match_time)
            db.add(match)
            await db.flush()
            db.add(MatchHistory(user_id=user_a_id, matched_with_user_id=user_b_id, match_id=match.id, created_at=match_time))
            db.add(MatchHistory(user_id=user_b_id, matched_with_user_id=user_a_id, match_id=match.id, created_at=match_time))

            # Every backfilled outcome respects the mystery's real time limit (difficulty-based,
            # mysteries/difficulty.py): solves land inside the window, and an EXPIRED session
            # ran the full clock down — exactly what production data looks like.
            time_limit = time_limit_for_difficulty(mystery.difficulty)
            limit_seconds = int(time_limit.total_seconds())
            roll = random.random()
            if roll < 0.68:
                status, result = "SOLVED", "solved"
                duration = timedelta(seconds=random.randint(int(limit_seconds * 0.15), int(limit_seconds * 0.95)))
            elif roll < 0.85:
                status, result = "EXPIRED", "expired"
                duration = time_limit
            else:
                status, result = "FAILED", "failed"
                duration = timedelta(seconds=random.randint(int(limit_seconds * 0.30), int(limit_seconds * 0.90)))
            ended_at = match_time + duration

            final_stage_number = max((s.stage_number for s in mystery.stages), default=1)
            session = MysterySession(
                match_id=match.id, mystery_id=mystery.id, player_a_id=user_a_id, player_b_id=user_b_id,
                status=status,
                current_stage_number=final_stage_number if status == "SOLVED" else random.randint(1, final_stage_number),
                started_at=match_time, expires_at=match_time + time_limit,
                solved_at=ended_at if status == "SOLVED" else None, ended_at=ended_at,
            )
            db.add(session)
            await db.flush()

            for uid in (user_a_id, user_b_id):
                db.add(UserMysteryHistory(
                    user_id=uid, mystery_id=mystery.id, session_id=session.id, category=mystery.category,
                    result=result, solve_seconds=duration.total_seconds() if status == "SOLVED" else None,
                    created_at=ended_at,
                ))

    await db.commit()
    total_activity_days = sum(len(v) for v in activity_by_day.values())
    print(f"Backfilled {total_activity_days} user-days of activity across {len(user_ids)} users.")


async def main() -> None:
    if settings.ENVIRONMENT != "development":
        # The one safeguard the product brief asks for: this script fabricates users, matches,
        # sessions and analytics, so it must be difficult to fire at a real deployment by accident.
        # There is no override flag on purpose — someone who genuinely needs demo data on a
        # non-development environment should set ENVIRONMENT=development for that run deliberately,
        # not flip a flag this script itself offers.
        print(
            f'Refusing to run: ENVIRONMENT is "{settings.ENVIRONMENT}", not "development".\n'
            "seed_demo.py creates FAKE users, matches, sessions, and activity — it must never "
            "touch a production database. Set ENVIRONMENT=development if this really is a "
            "development environment.",
            file=sys.stderr,
        )
        sys.exit(1)

    await seed_system_main()  # mysteries/badges/categories must exist before fake activity can reference them

    async with AsyncSessionLocal() as db:
        users = await seed_users(db)
        await seed_historical_engagement(db)
        print(f"Seeded {len(users)} users (or already present) and fabricated demo history.")
        print(f"Demo login: {settings.DEMO_USER_EMAIL} / {settings.DEMO_USER_PASSWORD}")
        print(f"Admin login: {settings.ADMIN_USER_EMAIL} / {settings.ADMIN_USER_PASSWORD}")
        print(f"All seed_user_* accounts use password: {settings.SEED_USER_PASSWORD}")
        print("\nDEVELOPMENT/DEMO DATA ONLY — none of this represents real user activity.")


if __name__ == "__main__":
    asyncio.run(main())
