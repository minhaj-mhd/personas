import asyncio
import os
import platform
import pytest
import pytest_asyncio
from sqlalchemy import delete

# Configure environment for testing
os.environ["TESTING"] = "true"
os.environ["GEMINI_API_KEY"] = "mock_key"

from app.db import engine, async_session_maker
from app.models.persona import Persona

# Set event loop policy at import time to prevent ProactorEventLoop issues on Windows
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture(scope="session", autouse=True)
async def clean_database_before_tests():
    """
    Ensures that the database has no custom personas from previous failed runs
    before any tests start executing.
    """
    async with async_session_maker() as session:
        try:
            await session.execute(delete(Persona).where(Persona.is_builtin == False))
            await session.commit()
            print("\nCleaned up legacy custom personas before starting tests.")
        except Exception as e:
            await session.rollback()
            print(f"\nWarning: Could not clean database before tests: {e}")
