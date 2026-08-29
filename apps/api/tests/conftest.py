"""
Every test in this suite talks to a REAL Postgres database (pairza_test)
and a REAL Redis instance — no mocking of the persistence layer, because
the invariants we care about (the matchmaking lock, the row-level
FOR UPDATE guard on session finalization, Postgres ARRAY columns) are
exactly the kind of thing a mocked DB would silently paper over.

Each test gets its OWN SQLAlchemy async engine, created and disposed
inside that single test's execution. asyncpg connections are bound to
the event loop they were created on, and pytest-asyncio does not
guarantee the same loop across fixtures/tests unless every layer is
pinned in lockstep — creating a short-lived engine per test sidesteps
that entirely instead of fighting loop-scope configuration.
"""
import os

os.environ["DATABASE_URL"] = "postgresql+asyncpg://postgres:pairza_dev_password@localhost:5432/pairza_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"  # separate Redis DB index from dev
os.environ["ENVIRONMENT"] = "test"

import pytest_asyncio
from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.common.security import hash_password
from app.models_registry import Base
from app.mysteries.models import Mystery, MysteryClue, MysteryStage
from app.users.models import Profile, User, UserPreferences

TEST_DATABASE_URL = os.environ["DATABASE_URL"]


@pytest_asyncio.fixture
async def db():
    """Fresh engine + schema + session for every single test — slower than
    sharing one engine, but immune to the entire class of asyncpg
    cross-event-loop bugs. Test DB is small, so the overhead is milliseconds."""
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    redis = from_url(os.environ["REDIS_URL"], decode_responses=True)
    await redis.flushdb()
    await redis.aclose()

    async with session_factory() as session:
        yield session

    await engine.dispose()


async def make_user(db, email: str, username: str, country_code: str = "US", **profile_kwargs) -> User:
    user = User(email=email, hashed_password=hash_password("TestPassword123!"), is_verified=True)
    db.add(user)
    await db.flush()
    db.add(Profile(user_id=user.id, username=username, country_code=country_code, **profile_kwargs))
    db.add(UserPreferences(user_id=user.id))
    await db.commit()
    await db.refresh(user)
    return user


async def make_mystery(
    db, title: str = "Test Mystery", category: str = "geo", difficulty: int = 1,
    final_answers: list[str] | None = None, two_stage: bool = False, is_published: bool = True,
) -> Mystery:
    mystery = Mystery(
        title=title, category=category, difficulty=difficulty,
        summary="A test mystery.", final_answer_patterns=final_answers or ["correct answer"],
        is_published=is_published,
    )
    db.add(mystery)
    await db.flush()

    if two_stage:
        stage1 = MysteryStage(mystery_id=mystery.id, stage_number=1, is_final=False, checkpoint_answer_patterns=["checkpoint"])
        db.add(stage1)
        await db.flush()
        db.add(MysteryClue(stage_id=stage1.id, role="player_a", text="Stage 1 clue for A"))
        db.add(MysteryClue(stage_id=stage1.id, role="player_b", text="Stage 1 clue for B"))

        stage2 = MysteryStage(mystery_id=mystery.id, stage_number=2, is_final=True)
        db.add(stage2)
        await db.flush()
        db.add(MysteryClue(stage_id=stage2.id, role="player_a", text="Stage 2 clue for A"))
        db.add(MysteryClue(stage_id=stage2.id, role="player_b", text="Stage 2 clue for B"))
    else:
        stage = MysteryStage(mystery_id=mystery.id, stage_number=1, is_final=True)
        db.add(stage)
        await db.flush()
        db.add(MysteryClue(stage_id=stage.id, role="player_a", text="Clue for A"))
        db.add(MysteryClue(stage_id=stage.id, role="player_b", text="Clue for B"))

    await db.commit()
    await db.refresh(mystery)
    return mystery
