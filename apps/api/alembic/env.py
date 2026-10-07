import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import get_settings
from app.models_registry import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()


def get_async_database_url() -> str:
    """
    Convert Railway's PostgreSQL URL to an asyncpg-compatible URL.

    Railway provides:
        postgresql://...

    SQLAlchemy async engine requires:
        postgresql+asyncpg://...
    """
    database_url = settings.DATABASE_URL

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+asyncpg://",
            1,
        )
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+asyncpg://",
            1,
        )

    return database_url


# Keep Alembic's configuration synchronized with the application settings.
config.set_main_option(
    "sqlalchemy.url",
    settings.DATABASE_URL,
)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""

    url = settings.DATABASE_URL

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """Run migrations using an active database connection."""

    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations using an asynchronous database connection."""

    database_url = get_async_database_url()

    connectable = create_async_engine(
        database_url,
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
