from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import NullPool
from app.config import settings

import os

# Check if running in test environment
is_testing = os.environ.get("TESTING", "false").lower() == "true"
pool_config = {"poolclass": NullPool} if is_testing else {}

# Create asynchronous engine for PostgreSQL
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    **pool_config
)

# Async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Base class for SQLAlchemy ORM models
class Base(DeclarativeBase):
    pass

# DB dependency for FastAPI routers
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    session = async_session_maker()
    try:
        yield session
    finally:
        await session.close()
