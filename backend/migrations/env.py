"""Alembic environment configuration for async SQLAlchemy.

Uses the run_sync() pattern required for async engines, as documented
in the Alembic async cookbook.

The DATABASE_URL is loaded from app.config.settings so it respects
the same .env file as the running application.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings

# Import Base *after* all models so metadata is populated.
from app.models import Base  # noqa: F401

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Inject the database URL from pydantic-settings (overrides alembic.ini value).
config.set_main_option("sqlalchemy.url", settings.database_url)

# Interpret the config file's logging settings.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata object used for autogenerate support.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode (generates SQL without a live DB connection)
# ---------------------------------------------------------------------------
def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode (requires a live DB connection)
# Uses run_sync() since Alembic doesn't natively await coroutines.
# ---------------------------------------------------------------------------
def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
