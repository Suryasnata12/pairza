
"""
Pairza integration-test infrastructure.

Every test uses real PostgreSQL and Redis.

Database schema:
    Created once per pytest session.

Database isolation:
    All application tables are truncated before each test.

Async engine:
    A separate engine is created and disposed for every test.
    This avoids sharing asyncpg connections across event loops.

Redis:
    Test database 1 is flushed before every test.
"""

import os

os.environ["DATABASE_URL"] = (
    "postgresql+asyncpg://postgres:pairza_dev_password"
    "@127.0.0.1:5432/pairza_test"
)
os.environ["REDIS_URL"] = "redis://127.0.0.1:6379/1"
os.environ["ENVIRONMENT"] = "test"

import pytest_asyncio

from redis.asyncio import from_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.common.security import hash_password
from app.models_registry import Base
from app.mysteries.models import Mystery, MysteryClue, MysteryStage
from app.users.models import Profile, User, UserPreferences


TEST_DATABASE_URL = os.environ["DATABASE_URL"]

TEST_PASSWORD = "TestPassword123!"
TEST_PASSWORD_HASH = hash_password(TEST_PASSWORD)


def _truncate_all_tables(sync_conn) -> None:
    """
    Remove all application data without dropping the schema.

    RESTART IDENTITY resets database-generated sequences.
    CASCADE handles foreign-key dependencies.
    Table names are quoted using SQLAlchemy's dialect preparer.
    """
    tables = Base.metadata.sorted_tables

    if not tables:
        return

    preparer = sync_conn.dialect.identifier_preparer

    table_names = ", ".join(
        preparer.format_table(table)
        for table in tables
    )

    sync_conn.exec_driver_sql(
        f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_schema():
    engine = create_async_engine(TEST_DATABASE_URL)

    try:

        async with engine.begin() as conn:

            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
            
        yield

    finally:
        await engine.dispose()
        
@pytest_asyncio.fixture
async def db(test_schema):

    # 1. Engine creation
    engine = create_async_engine(TEST_DATABASE_URL)

    try:
        # 2. PostgreSQL connection

        async with engine.begin() as conn:
            
            # 3. Database cleanup

            await conn.run_sync(_truncate_all_tables)


        # 4. Redis cleanup

        redis = from_url(
            os.environ["REDIS_URL"],
            decode_responses=True,
        )

        try:
            await redis.flushdb()
        finally:
            await redis.aclose()


        # 5. Create test session
        session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

        async with session_factory() as session:

            yield session

    finally:
        await engine.dispose()

async def make_user(
    db,
    email: str,
    username: str,
    country_code: str = "US",
    **profile_kwargs,
) -> User:
    """Create a verified user with profile and preferences."""

    user = User(
        email=email,
        hashed_password=TEST_PASSWORD_HASH,
        is_verified=True,
    )

    db.add(user)
    await db.flush()

    db.add(
        Profile(
            user_id=user.id,
            username=username,
            country_code=country_code,
            **profile_kwargs,
        )
    )

    db.add(UserPreferences(user_id=user.id))

    await db.commit()
    await db.refresh(user)

    return user


async def make_mystery(
    db,
    title: str = "Test Mystery",
    category: str = "geo",
    difficulty: int = 1,
    final_answers: list[str] | None = None,
    two_stage: bool = False,
    is_published: bool = True,
) -> Mystery:
    """Create a mystery with its stages and clues."""

    mystery = Mystery(
        title=title,
        category=category,
        difficulty=difficulty,
        summary="A test mystery.",
        final_answer_patterns=final_answers or ["correct answer"],
        is_published=is_published,
        status="PUBLISHED" if is_published else "DRAFT",
    )

    db.add(mystery)
    await db.flush()

    if two_stage:
        stage1 = MysteryStage(
            mystery_id=mystery.id,
            stage_number=1,
            is_final=False,
            checkpoint_answer_patterns=["checkpoint"],
        )

        db.add(stage1)
        await db.flush()

        db.add(
            MysteryClue(
                stage_id=stage1.id,
                role="player_a",
                text="Stage 1 clue for A",
            )
        )

        db.add(
            MysteryClue(
                stage_id=stage1.id,
                role="player_b",
                text="Stage 1 clue for B",
            )
        )

        stage2 = MysteryStage(
            mystery_id=mystery.id,
            stage_number=2,
            is_final=True,
        )

        db.add(stage2)
        await db.flush()

        db.add(
            MysteryClue(
                stage_id=stage2.id,
                role="player_a",
                text="Stage 2 clue for A",
            )
        )

        db.add(
            MysteryClue(
                stage_id=stage2.id,
                role="player_b",
                text="Stage 2 clue for B",
            )
        )

    else:
        stage = MysteryStage(
            mystery_id=mystery.id,
            stage_number=1,
            is_final=True,
        )

        db.add(stage)
        await db.flush()

        db.add(
            MysteryClue(
                stage_id=stage.id,
                role="player_a",
                text="Clue for A",
            )
        )

        db.add(
            MysteryClue(
                stage_id=stage.id,
                role="player_b",
                text="Clue for B",
            )
        )

    await db.commit()
    await db.refresh(mystery)

    return mystery
