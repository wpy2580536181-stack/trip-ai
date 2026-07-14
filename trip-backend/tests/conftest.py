"""Shared fixtures for pytest"""

import sys
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
from src.models.feedback import Feedback
from src.models.agent_step import AgentStep
from src.models.token_usage_log import TokenUsageLog

# Ensure all models are imported so Base.metadata knows about them
import src.models.user
import src.models.conversation
import src.models.message
import src.models.trip
import src.models.spot
import src.models.password_reset
import src.models.role
import src.models.feedback
import src.models.agent_step
import src.models.token_usage_log


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
    """Create test database tables once per session"""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
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


# Cache real module references before any test can mock them
_real_module_cache = {}
for _mod_name in ("torch", "chromadb", "sentence_transformers"):
    try:
        import importlib
        _real_module_cache[_mod_name] = importlib.import_module(_mod_name)
    except Exception:
        pass  # Module not installed or import fails


@pytest.fixture(autouse=True)
def ensure_real_modules_sync():
    """Sync autouse fixture to ensure heavy modules are real before each test.

    test_agent_imports.py mocks torch/chromadb/sentence_transformers in sys.modules.
    This fixture restores the real modules that were cached at import time.
    """
    from unittest.mock import MagicMock

    for name in ("torch", "chromadb", "sentence_transformers"):
        mod = sys.modules.get(name)
        if isinstance(mod, MagicMock):
            # Restore the real module from our cache
            real_mod = _real_module_cache.get(name)
            if real_mod is not None:
                sys.modules[name] = real_mod
            else:
                sys.modules.pop(name, None)

            # Also fix sub-modules
            for key in list(sys.modules.keys()):
                if key.startswith(name + ".") and isinstance(sys.modules[key], MagicMock):
                    sys.modules.pop(key, None)

    yield


@pytest_asyncio.fixture(autouse=True)
async def reset_rate_limiters():
    """Reset all rate limiter stores before each test to prevent 429 errors.

    Also patches the RateLimiter class so new instances (like the
    GlobalRateLimitMiddleware's limiter) are effectively unlimited during tests.
    """
    from src.middleware.rate_limiter import (
        RateLimiter,
        auth_rate_limiter,
        feedback_rate_limiter,
        knowledge_rate_limiter,
        chat_rate_limiter,
        recommend_rate_limiter,
        optimize_rate_limiter,
    )

    limiters = [
        auth_rate_limiter,
        feedback_rate_limiter,
        knowledge_rate_limiter,
        chat_rate_limiter,
        recommend_rate_limiter,
        optimize_rate_limiter,
    ]

    # Clear all known limiter stores and set very high limits
    for limiter in limiters:
        if hasattr(limiter.store, "_data"):
            limiter.store._data.clear()
        limiter.max_requests = 999999

    # Patch RateLimiter.__init__ so new instances (like the
    # GlobalRateLimitMiddleware's internal limiter) are also unlimited
    _orig_init = RateLimiter.__init__

    def _test_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        self.max_requests = 999999
        if hasattr(self.store, "_data"):
            self.store._data.clear()

    RateLimiter.__init__ = _test_init

    yield

    # Restore original init
    RateLimiter.__init__ = _orig_init

    # Clear stores after test
    for limiter in limiters:
        if hasattr(limiter.store, "_data"):
            limiter.store._data.clear()


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


# ---------------------------------------------------------------------------
# Additional test fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def authenticated_client(async_client: AsyncClient, mock_user: User) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient with JWT token auto-injected for mock_user"""
    from src.utils.security import create_access_token

    token = create_access_token(
        user_id=mock_user.id,
        username=mock_user.username,
        role_id=mock_user.role_id,
    )
    async_client.headers["Authorization"] = f"Bearer {token}"
    yield async_client
    del async_client.headers["Authorization"]


@pytest_asyncio.fixture
async def mock_llm():
    """Mock LLM that returns deterministic responses"""
    from unittest.mock import AsyncMock, patch, MagicMock

    mock_response = MagicMock()
    mock_response.content = "这是 mock LLM 的响应"
    mock_response.usage_metadata = {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
    }

    mock_chat_model = AsyncMock()
    mock_chat_model.ainvoke = AsyncMock(return_value=mock_response)
    mock_chat_model.astream = AsyncMock(return_value=iter([mock_response]))

    with patch("src.config.llm.get_llm", return_value=mock_chat_model):
        yield mock_chat_model


@pytest.fixture
def mock_redis():
    """In-memory Redis mock"""
    from unittest.mock import AsyncMock, patch

    store: dict = {}
    mock_redis_client = AsyncMock()
    mock_redis_client.get = AsyncMock(side_effect=lambda k: store.get(k))
    mock_redis_client.set = AsyncMock(side_effect=lambda k, v, **kw: store.update({k: v}))
    mock_redis_client.delete = AsyncMock(side_effect=lambda k: store.pop(k, None))
    mock_redis_client.exists = AsyncMock(side_effect=lambda k: k in store)
    mock_redis_client.expire = AsyncMock()
    mock_redis_client.incr = AsyncMock(
        side_effect=lambda k: store.update({k: store.get(k, 0) + 1}) or store[k]
    )
    mock_redis_client.llen = AsyncMock(side_effect=lambda k: len(store.get(k, [])))
    mock_redis_client.lrange = AsyncMock(
        side_effect=lambda k, s, e: (
            store.get(k, [])[s : e + 1] if e >= 0 else store.get(k, [])
        )
    )
    mock_redis_client.rpush = AsyncMock(
        side_effect=lambda k, v: store.setdefault(k, []).append(v)
    )
    mock_redis_client.pipeline = AsyncMock()

    with patch("src.config.redis_client.get_redis", return_value=mock_redis_client):
        yield mock_redis_client
