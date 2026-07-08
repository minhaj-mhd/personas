import asyncio
import os
import platform
import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import create_async_engine

# Configure environment for testing BEFORE any app module is imported —
# app.config reads TESTING at import time and redirects DATABASE_URL to the
# isolated "<dbname>_test" database.
os.environ["TESTING"] = "true"
os.environ["GEMINI_API_KEY"] = "mock_key"

from app.config import settings
from app.db import engine, async_session_maker, Base
from app.models import Persona, Conversation, Message, Memory  # noqa: F401 — register all tables on Base.metadata

# Set event loop policy at import time to prevent ProactorEventLoop issues on Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"


@pytest_asyncio.fixture(scope="session", autouse=True)
async def prepare_test_database():
    """
    Creates the isolated test database (if missing), builds the schema from the
    ORM models, and starts from empty tables. The dev database is never touched.
    """
    if not (settings.TESTING and settings.DATABASE_URL.endswith("_test")):
        pytest.exit(
            f"Refusing to run: tests must use a '_test' database, got {settings.DATABASE_URL}",
            returncode=1,
        )

    base_url, _, test_dbname = settings.DATABASE_URL.rpartition("/")

    # Create the test database via the always-present 'postgres' maintenance DB
    admin_engine = create_async_engine(
        f"{base_url}/postgres", isolation_level="AUTOCOMMIT"
    )
    async with admin_engine.connect() as conn:
        exists = await conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": test_dbname},
        )
        if not exists:
            await conn.execute(text(f'CREATE DATABASE "{test_dbname}"'))
    await admin_engine.dispose()

    # Build/refresh schema and start clean
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_maker() as session:
        await session.execute(delete(Memory))
        await session.execute(delete(Message))
        await session.execute(delete(Conversation))
        await session.execute(delete(Persona))
        await session.commit()
