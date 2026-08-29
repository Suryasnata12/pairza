"""
Async SQLAlchemy setup shared by every module.

One engine, one sessionmaker, one declarative Base. Feature modules import
`Base` to declare their models and `get_db` as a FastAPI dependency to get
a request-scoped AsyncSession.
"""
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config.settings import get_settings

settings = get_settings()

from sqlalchemy.pool import NullPool

_engine_kwargs: dict = dict(echo=False, pool_pre_ping=True)
if settings.ENVIRONMENT == "test":
    # NullPool: every checkout is a brand-new connection, never reused
    # across an event loop boundary. pytest-asyncio can spin up more than
    # one event loop over a test session, and a pooled asyncpg connection
    # bound to a now-dead loop raises cryptic "attached to a different
    # loop" errors — NullPool sidesteps the whole problem in exchange for
    # a bit of extra connection overhead, which only matters at test scale.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base — every ORM model in the app inherits this."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a request-scoped DB session and guarantees cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
