"""Shared fixtures for pytest"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator, Generator

from src.main import app
from src.models.base import Base
from src.config.database import get_db
from src.models.user import User
from src.models.conversation import Conversation
from src.models.message import Message
from src.models.trip import Trip
from src.models.spot import Spot
from src.models.password_reset import PasswordReset


# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

# Create test engine
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Create test session factory
TestSessionLocal = sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest_asyncio.fixture(scope="session")
async def setup_database():
    """Create test database tables"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_database) -> AsyncGenerator[AsyncSession, None]:
    """Create a fresh database session for each test"""
    async with TestSessionLocal() as session:
        yield session
        # Rollback any uncommitted changes
        await session.rollback()
        
        # Clean up all data after each test
        from sqlalchemy import text
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(text(f"DELETE FROM {table.name}"))
        await session.commit()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for FastAPI"""
    
    # Override the get_db dependency to use test database
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        yield client
    
    app.dependency_overrides.clear()


@pytest.fixture
def mock_user():
    """Create a mock user for testing"""
    return User(
        id=1,
        username="testuser",
        email="test@example.com",
        password="hashed_password",
        nickname="Test User",
        avatar=None,
        role_id=2,
        status=1
    )


@pytest.fixture
def mock_admin_user():
    """Create a mock admin user for testing"""
    return User(
        id=2,
        username="admin",
        email="admin@example.com",
        password="hashed_password",
        nickname="Admin",
        avatar=None,
        role_id=1,
        status=1
    )
