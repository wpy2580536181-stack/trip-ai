"""Comprehensive middleware unit tests.

Covers: auth, rate_limiter, idempotency, concurrency_guard,
        token_budget_guard, exception_handlers.
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.responses import Response

from src.config.settings import settings
from src.utils.security import create_access_token, decode_token
from src.exceptions import AppException, UnauthorizedException

# ────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────


def _make_request(
    method: str = "GET",
    path: str = "/api/test",
    headers: dict | None = None,
    user=None,
    client_host: str = "127.0.0.1",
) -> MagicMock:
    """Build a mock FastAPI Request."""
    req = MagicMock(spec=Request)
    req.method = method
    req.url = MagicMock()
    req.url.path = path
    req.headers = headers or {}
    req.client = MagicMock()
    req.client.host = client_host

    # request.state
    state = MagicMock()
    state.user = user
    req.state = state
    return req


# ────────────────────────────────────────────
# 1. auth.py tests  (decode_token / require_admin / get_current_user)
# ────────────────────────────────────────────


class TestDecodeToken:
    """Tests for src.utils.security.decode_token."""

    def test_decode_token_valid(self):
        token = create_access_token(user_id=1, username="alice", role_id=2)
        payload = decode_token(token)
        assert payload["userId"] == 1
        assert payload["username"] == "alice"
        assert payload["roleId"] == 2

    def test_decode_token_expired(self):
        # Build a token that expired 1 hour ago
        payload = {
            "userId": 1,
            "username": "alice",
            "roleId": 2,
            "exp": time.time() - 3600,
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        with pytest.raises(Exception):
            decode_token(token)

    def test_decode_token_tampered(self):
        token = create_access_token(user_id=1, username="alice", role_id=2)
        # Flip a character in the signature portion
        parts = token.split(".")
        sig = parts[2]
        tampered_sig = sig[:-1] + ("A" if sig[-1] != "A" else "B")
        tampered_token = f"{parts[0]}.{parts[1]}.{tampered_sig}"
        with pytest.raises(Exception):
            decode_token(tampered_token)

    def test_decode_token_invalid_format(self):
        with pytest.raises(Exception):
            decode_token("not.a.jwt")

    def test_decode_token_missing_fields(self):
        # Token without userId field
        payload = {
            "username": "alice",
            "exp": time.time() + 3600,
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        result = decode_token(token)
        # decode_token returns the raw payload — it doesn't validate fields
        assert "userId" not in result


class TestRequireAdmin:
    """Tests for src.middleware.auth.require_admin."""

    def test_require_admin_success(self, mock_admin_user):
        from src.middleware.auth import require_admin

        # require_admin is a plain function (not async) that checks role_id == 1
        result = require_admin(mock_admin_user)
        assert result == mock_admin_user

    def test_require_admin_forbidden(self, mock_user):
        from src.middleware.auth import require_admin

        with pytest.raises(HTTPException) as exc_info:
            require_admin(mock_user)
        assert exc_info.value.status_code == 403


class TestGetCurrentUser:
    """Tests for src.middleware.auth.get_current_user (JWT decode path)."""

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self, mock_user):
        """Valid token should decode and attempt DB lookup.

        We patch the DB session to return the mock user.
        """
        from src.middleware.auth import get_current_user
        from fastapi.security import HTTPAuthorizationCredentials

        token = create_access_token(user_id=1, username="testuser", role_id=2)
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer", credentials=token
        )

        # Mock the DB session context manager
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_user
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("src.middleware.auth.async_session", return_value=mock_cm):
            req = _make_request()
            user = await get_current_user(request=req, credentials=credentials)
            assert user == mock_user


# ────────────────────────────────────────────
# 2. rate_limiter.py tests
# ────────────────────────────────────────────


class TestMemoryStore:
    """Tests for the rate limiter MemoryStore."""

    @pytest.mark.asyncio
    async def test_memory_store_increment(self):
        from src.middleware.rate_limiter import MemoryStore

        store = MemoryStore()
        count1, _ = await store.increment("k1", 60)
        count2, _ = await store.increment("k1", 60)
        assert count1 == 1
        assert count2 == 2

    @pytest.mark.asyncio
    async def test_memory_store_reset(self):
        from src.middleware.rate_limiter import MemoryStore

        store = MemoryStore()
        await store.increment("k1", 60)
        await store.increment("k1", 60)
        await store.reset_key("k1")
        count, _ = await store.increment("k1", 60)
        assert count == 1

    @pytest.mark.asyncio
    async def test_memory_store_expiry(self):
        from src.middleware.rate_limiter import MemoryStore

        store = MemoryStore()
        # Use a very short window
        count1, reset_at = await store.increment("k1", 0.01)
        assert count1 == 1

        # Wait for window to expire
        await asyncio.sleep(0.05)

        count2, _ = await store.increment("k1", 0.01)
        assert count2 == 1  # Window expired, counter reset


class TestRateLimiter:
    """Tests for the RateLimiter dependency."""

    @pytest.mark.asyncio
    async def test_rate_limiter_pass(self):
        from src.middleware.rate_limiter import RateLimiter, MemoryStore

        store = MemoryStore()
        limiter = RateLimiter(max_requests=5, window_seconds=60, store=store)
        req = _make_request()
        await limiter(req)  # Should not raise

    @pytest.mark.asyncio
    async def test_rate_limiter_exceeded(self):
        from src.middleware.rate_limiter import RateLimiter, MemoryStore

        store = MemoryStore()
        limiter = RateLimiter(max_requests=2, window_seconds=60, store=store)
        # Override conftest's autouse patch that forces max_requests=999999
        limiter.max_requests = 2
        req = _make_request()

        await limiter(req)  # 1
        await limiter(req)  # 2
        with pytest.raises(HTTPException) as exc_info:
            await limiter(req)  # 3 → 429
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_rate_limiter_different_keys(self):
        from src.middleware.rate_limiter import RateLimiter, MemoryStore

        store = MemoryStore()
        limiter = RateLimiter(
            max_requests=1,
            window_seconds=60,
            key_func=lambda r: r.headers.get("x-key", "default"),
            store=store,
        )
        # Override conftest's autouse patch
        limiter.max_requests = 1

        req_a = _make_request(headers={"x-key": "a"})
        req_b = _make_request(headers={"x-key": "b"})

        await limiter(req_a)  # key "a" → 1
        await limiter(req_b)  # key "b" → 1 (independent)

        # Both should be at limit=1 now, next call for "a" should fail
        with pytest.raises(HTTPException):
            await limiter(req_a)

    @pytest.mark.asyncio
    async def test_rate_limiter_response_headers(self):
        from src.middleware.rate_limiter import RateLimiter, MemoryStore

        store = MemoryStore()
        limiter = RateLimiter(max_requests=10, window_seconds=60, store=store)
        # Override conftest's autouse patch
        limiter.max_requests = 10
        req = _make_request()
        await limiter(req)

        headers = req.state.rate_limit_headers
        assert "X-RateLimit-Limit" in headers
        assert headers["X-RateLimit-Limit"] == "10"
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers


class TestGlobalRateLimitMiddleware:
    """Tests for GlobalRateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_rate_limit_global_middleware_non_api(self):
        """Non-/api paths should pass through without rate limiting."""
        from src.middleware.rate_limiter import GlobalRateLimitMiddleware

        async def simple_app(scope, receive, send):
            pass

        middleware = GlobalRateLimitMiddleware(simple_app, max_requests=1, window_seconds=60)

        # Build a real-ish ASGI scope for a non-/api path
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/health",
            "headers": [],
            "query_string": b"",
            "root_path": "",
            "server": ("testserver", 80),
        }

        # The middleware should call call_next without rate-limiting
        call_next_called = False

        async def call_next(request):
            nonlocal call_next_called
            call_next_called = True
            return Response(content="ok", status_code=200)

        from starlette.requests import Request as StarletteRequest

        req = StarletteRequest(scope)
        response = await middleware.dispatch(req, call_next)
        assert call_next_called
        assert response.status_code == 200


# ────────────────────────────────────────────
# 3. idempotency.py tests
# ────────────────────────────────────────────


class TestIdempotency:
    """Tests for IdempotencyMiddleware & MemoryIdempotencyStore."""

    @pytest.mark.asyncio
    async def test_idempotency_first_request(self):
        from src.middleware.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore

        store = MemoryIdempotencyStore(ttl_s=3600)
        app = AsyncMock()

        # call_next returns a streaming response
        async def body_iter():
            yield b'{"result": "ok"}'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.body_iterator = body_iter()
        mock_response.headers = {}
        mock_response.media_type = "application/json"
        app.return_value = mock_response

        middleware = IdempotencyMiddleware(app, store=store)

        req = _make_request(method="POST", headers={"idempotency-key": "abc123"})
        response = await middleware.dispatch(req, app)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_idempotency_cached_response(self):
        from src.middleware.idempotency import (
            IdempotencyMiddleware,
            MemoryIdempotencyStore,
            CachedResponse,
        )

        store = MemoryIdempotencyStore(ttl_s=3600)
        # Pre-populate cache
        await store.set(
            "anonymous:dup-key",
            CachedResponse(
                status_code=200,
                body='{"cached": true}',
                created_at=time.time(),
            ),
        )

        app = AsyncMock()
        middleware = IdempotencyMiddleware(app, store=store)

        req = _make_request(method="POST", headers={"idempotency-key": "dup-key"})
        response = await middleware.dispatch(req, app)

        # Should return cached response, not call app
        assert response.status_code == 200
        app.assert_not_called()

    @pytest.mark.asyncio
    async def test_idempotency_different_keys(self):
        from src.middleware.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore

        store = MemoryIdempotencyStore(ttl_s=3600)

        call_count = 0

        async def mock_app(request):
            nonlocal call_count
            call_count += 1

            async def body_iter():
                yield json.dumps({"call": call_count}).encode()

            resp = MagicMock()
            resp.status_code = 200
            resp.body_iterator = body_iter()
            resp.headers = {}
            resp.media_type = "application/json"
            return resp

        middleware = IdempotencyMiddleware(mock_app, store=store)

        req1 = _make_request(method="POST", headers={"idempotency-key": "key-1"})
        await middleware.dispatch(req1, mock_app)

        req2 = _make_request(method="POST", headers={"idempotency-key": "key-2"})
        await middleware.dispatch(req2, mock_app)

        assert call_count == 2  # Both executed

    @pytest.mark.asyncio
    async def test_idempotency_no_header(self):
        from src.middleware.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore

        store = MemoryIdempotencyStore(ttl_s=3600)
        app = AsyncMock(return_value=Response(content="ok", status_code=200))
        middleware = IdempotencyMiddleware(app, store=store)

        req = _make_request(method="POST")  # No idempotency-key header
        response = await middleware.dispatch(req, app)

        app.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_non_2xx_not_cached(self):
        """Non-2xx responses must NOT be cached."""
        from src.middleware.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore

        store = MemoryIdempotencyStore(ttl_s=3600)

        async def error_app(request):
            return Response(content="error", status_code=500)

        middleware = IdempotencyMiddleware(error_app, store=store)

        req = _make_request(method="POST", headers={"idempotency-key": "fail-key"})
        response = await middleware.dispatch(req, error_app)

        assert response.status_code == 500

        # Store should be empty — non-2xx not cached
        cached = await store.get("anonymous:fail-key")
        assert cached is None

    @pytest.mark.asyncio
    async def test_idempotency_ttl_expiry(self):
        from src.middleware.idempotency import MemoryIdempotencyStore, CachedResponse

        store = MemoryIdempotencyStore(ttl_s=0.05)  # 50ms TTL

        await store.set(
            "anon:ttl-key",
            CachedResponse(status_code=200, body="{}", created_at=time.time()),
        )

        # Should be cached immediately
        result = await store.get("anon:ttl-key")
        assert result is not None

        # Wait for TTL expiry
        await asyncio.sleep(0.1)

        result = await store.get("anon:ttl-key")
        assert result is None

    @pytest.mark.asyncio
    async def test_idempotency_path_prefix_filter(self):
        """Requests outside path_prefixes should skip idempotency logic."""
        from src.middleware.idempotency import IdempotencyMiddleware, MemoryIdempotencyStore

        store = MemoryIdempotencyStore(ttl_s=3600)

        call_count = 0

        async def mock_app(request):
            nonlocal call_count
            call_count += 1
            return Response(content="ok", status_code=200)

        middleware = IdempotencyMiddleware(
            mock_app,
            store=store,
            path_prefixes=["/api/chat"],
        )

        # POST to /api/other (NOT in prefix list) — should always execute
        req1 = _make_request(method="POST", path="/api/other", headers={"idempotency-key": "x"})
        await middleware.dispatch(req1, mock_app)

        req2 = _make_request(method="POST", path="/api/other", headers={"idempotency-key": "x"})
        await middleware.dispatch(req2, mock_app)

        assert call_count == 2  # Both executed — no caching for non-matching prefix


# ────────────────────────────────────────────
# 4. concurrency_guard.py tests
# ────────────────────────────────────────────


class TestConcurrencyGuard:
    """Tests for concurrency_guard_dependency and ConcurrencyGuardMiddleware."""

    @pytest.mark.asyncio
    async def test_concurrency_acquire_release(self):
        from src.middleware.concurrency_guard import concurrency_guard_dependency

        req = _make_request()
        req.state.user = None

        await concurrency_guard_dependency(req)

        assert hasattr(req.state, "_concurrency_release")
        assert callable(req.state._concurrency_release)

        # Release to clean up
        await req.state._concurrency_release()

    @pytest.mark.asyncio
    async def test_concurrency_exceeded(self):
        from src.middleware.concurrency_guard import concurrency_guard_dependency
        from src.services.agent.semaphore import ConcurrencyGuard

        # Create a guard with per_user_max=1 so second acquire fails
        guard = ConcurrencyGuard(global_max=10, per_user_max=1)

        with patch(
            "src.middleware.concurrency_guard.concurrency_guard", guard
        ):
            req1 = _make_request()
            req1.state.user = MagicMock(id=99)
            await concurrency_guard_dependency(req1)

            # Second request from same user should fail (per_user_max=1)
            req2 = _make_request()
            req2.state.user = MagicMock(id=99)
            with pytest.raises(HTTPException) as exc_info:
                await concurrency_guard_dependency(req2)
            assert exc_info.value.status_code == 429

            # Clean up first request
            await req1.state._concurrency_release()

    @pytest.mark.asyncio
    async def test_concurrency_release_on_error(self):
        """ConcurrencyGuardMiddleware should release in finally block."""
        from src.middleware.concurrency_guard import ConcurrencyGuardMiddleware
        from src.services.agent.semaphore import ConcurrencyGuard

        guard = ConcurrencyGuard(global_max=10, per_user_max=1)

        async def failing_call_next(request):
            raise RuntimeError("boom")

        middleware = ConcurrencyGuardMiddleware.__new__(ConcurrencyGuardMiddleware)

        req = _make_request()
        req.state.user = MagicMock(id=42)

        with patch(
            "src.middleware.concurrency_guard.concurrency_guard", guard
        ):
            with pytest.raises(RuntimeError):
                await middleware.dispatch(req, failing_call_next)

            # After error, the semaphore should have been released.
            # We can verify by acquiring again for the same user.
            success, release = await guard.try_acquire(42)
            assert success is True
            await release()

    @pytest.mark.asyncio
    async def test_concurrency_global_limit(self):
        """When global semaphore is exhausted, new requests get 429."""
        from src.middleware.concurrency_guard import concurrency_guard_dependency
        from src.services.agent.semaphore import ConcurrencyGuard

        # global_max=1 so only one concurrent request across ALL users
        guard = ConcurrencyGuard(global_max=1, per_user_max=1)

        with patch(
            "src.middleware.concurrency_guard.concurrency_guard", guard
        ):
            # User A acquires the single global slot
            req_a = _make_request()
            req_a.state.user = MagicMock(id=100)
            await concurrency_guard_dependency(req_a)

            # User B should be rejected (global exhausted)
            req_b = _make_request()
            req_b.state.user = MagicMock(id=200)
            with pytest.raises(HTTPException) as exc_info:
                await concurrency_guard_dependency(req_b)
            assert exc_info.value.status_code == 429

            # Cleanup
            await req_a.state._concurrency_release()


# ────────────────────────────────────────────
# 5. token_budget_guard.py tests
# ────────────────────────────────────────────


class TestTokenBudgetGuard:
    """Tests for token_budget_guard_dependency."""

    @pytest.mark.asyncio
    async def test_budget_check_pass(self):
        from src.middleware.token_budget_guard import token_budget_guard_dependency
        from src.services.agent.token_budget import TokenBudgetManager

        manager = TokenBudgetManager(user_token_limit=10000, global_token_limit=50000)

        with patch(
            "src.middleware.token_budget_guard.token_budget_manager", manager
        ):
            req = _make_request()
            req.state.user = MagicMock(id=1)
            await token_budget_guard_dependency(req)  # Should not raise

    @pytest.mark.asyncio
    async def test_budget_check_user_exceeded(self):
        from src.middleware.token_budget_guard import token_budget_guard_dependency
        from src.services.agent.token_budget import TokenBudgetManager

        manager = TokenBudgetManager(user_token_limit=100, global_token_limit=50000)

        with patch(
            "src.middleware.token_budget_guard.token_budget_manager", manager
        ):
            # Exhaust user budget
            await manager.record_user_usage(1, 200)

            req = _make_request()
            req.state.user = MagicMock(id=1)
            with pytest.raises(HTTPException) as exc_info:
                await token_budget_guard_dependency(req)
            assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_budget_check_global_exceeded(self):
        from src.middleware.token_budget_guard import token_budget_guard_dependency
        from src.services.agent.token_budget import TokenBudgetManager

        manager = TokenBudgetManager(user_token_limit=50000, global_token_limit=100)

        with patch(
            "src.middleware.token_budget_guard.token_budget_manager", manager
        ):
            # Exhaust global budget
            await manager.record_global_usage(200)

            req = _make_request()
            req.state.user = MagicMock(id=2)
            with pytest.raises(HTTPException) as exc_info:
                await token_budget_guard_dependency(req)
            assert exc_info.value.status_code == 503


# ────────────────────────────────────────────
# 6. exception_handlers.py tests
# ────────────────────────────────────────────


class TestExceptionHandlers:
    """Tests for global exception handlers registered via setup_exception_handlers."""

    @pytest.fixture
    def client(self):
        """Create a test client with exception handlers registered."""
        app = FastAPI()

        from src.middleware.exception_handlers import setup_exception_handlers

        setup_exception_handlers(app)

        @app.get("/raise-http")
        async def raise_http():
            raise AppException(
                status_code=400, code=400, message="Bad request", error="BAD_REQUEST"
            )

        @app.get("/raise-generic")
        async def raise_generic():
            raise RuntimeError("unexpected error")

        @app.get("/raise-format-a")
        async def raise_format_a():
            raise AppException(
                status_code=400, code=400, message="Bad input", error="BAD_INPUT"
            )

        return TestClient(app, raise_server_exceptions=False)

    def test_http_exception_handler(self, client):
        resp = client.get("/raise-http")
        assert resp.status_code == 400
        body = resp.json()
        assert body["code"] == 400
        assert body["message"] == "Bad request"
        assert body["error"] == "BAD_REQUEST"

    def test_validation_exception_handler(self, client):
        """Pydantic / FastAPI validation errors should return 422."""
        app = FastAPI()
        from src.middleware.exception_handlers import setup_exception_handlers
        from fastapi import Query

        setup_exception_handlers(app)

        @app.get("/validate")
        async def validate(age: int = Query(ge=0)):
            return {"age": age}

        vc = TestClient(app, raise_server_exceptions=False)
        resp = vc.get("/validate?age=-1")
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_generic_exception_handler(self, client):
        resp = client.get("/raise-generic")
        assert resp.status_code == 500
        body = resp.json()
        assert body["code"] == 500

    def test_format_a_exception_handler(self, client):
        """Paths like /api/trip/recommend use format A: {success, data, error}."""
        app = FastAPI()
        from src.middleware.exception_handlers import setup_exception_handlers

        setup_exception_handlers(app)

        @app.get("/api/trip/recommend")
        async def recommend():
            raise AppException(
                status_code=400, code=400, message="Bad input", error="BAD_INPUT"
            )

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/trip/recommend")
        assert resp.status_code == 400
        body = resp.json()
        assert body["success"] is False
        assert body["error"] == "Bad input"
        assert "code" not in body
