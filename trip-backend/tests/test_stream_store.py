"""StreamStore + SSE 续传工具单元测试。

测试内容：
- stream_store: create / append_event / get_events_since / mark_complete / delete
- utils.stream: sse_event / sse_end_event / create_resumable_stream / resume_stream
- 内存降级模式（Redis 不可用）
- IDOR 防护（stream owner != requester → StreamForbiddenError）
"""

import sys
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

# 确保 Redis 不可用（内存降级模式）
sys.modules.setdefault("src.config.redis_client", MagicMock())


from src.services import stream_store
from src.services.stream_store import (
    create_stream,
    append_event,
    get_events_since,
    get_stream_state,
    mark_complete,
    delete_stream,
    cleanup_expired,
    _memory_store,
    CreateStreamResult,
    StreamEvent,
    StreamState,
)
from src.utils.stream import (
    sse_event,
    sse_end_event,
    sse_error_event,
    create_resumable_stream,
    resume_stream,
    StreamNotFoundError,
    StreamForbiddenError,
    StreamBadRequestError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def clear_memory_store():
    """每个测试前后清空内存存储，确保隔离。"""
    _memory_store.clear()
    yield
    _memory_store.clear()


# ---------------------------------------------------------------------------
# stream_store 基础操作
# ---------------------------------------------------------------------------

class TestStreamStore:
    """StreamStore 内存降级模式测试。"""

    @pytest.mark.asyncio
    async def test_create_stream(self):
        """测试创建 stream。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        assert isinstance(result, CreateStreamResult)
        assert result.stream_id.startswith("stream:")
        assert result.seq == 0

    @pytest.mark.asyncio
    async def test_append_event(self):
        """测试追加 event。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        seq1 = await append_event(sid, "delta", {"content": "hello"})
        assert seq1 == 1

        seq2 = await append_event(sid, "delta", {"content": " world"})
        assert seq2 == 2

    @pytest.mark.asyncio
    async def test_get_events_since_zero(self):
        """测试获取所有 events（last_seq=0）。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await append_event(sid, "delta", {"content": "a"})
        await append_event(sid, "delta", {"content": "b"})
        await append_event(sid, "complete", {"done": True})

        events = await get_events_since(sid, last_seq=0)
        assert len(events) == 3
        assert events[0].seq == 1
        assert events[0].type == "delta"
        assert events[2].type == "complete"

    @pytest.mark.asyncio
    async def test_get_events_since_partial(self):
        """测试从指定 seq 开始获取 events。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await append_event(sid, "delta", {"content": "a"})
        await append_event(sid, "delta", {"content": "b"})
        await append_event(sid, "complete", {"done": True})

        events = await get_events_since(sid, last_seq=2)
        assert len(events) == 1
        assert events[0].seq == 3
        assert events[0].type == "complete"

    @pytest.mark.asyncio
    async def test_get_events_since_empty(self):
        """测试 last_seq >= total_seq 时返回空。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await append_event(sid, "delta", {"content": "a"})

        events = await get_events_since(sid, last_seq=1)
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_get_events_since_exceeds(self):
        """测试 last_seq > total_seq 时抛出 ValueError。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await append_event(sid, "delta", {"content": "a"})

        with pytest.raises(ValueError, match="exceeds"):
            await get_events_since(sid, last_seq=100)

    @pytest.mark.asyncio
    async def test_get_stream_state(self):
        """测试获取 stream 状态。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await append_event(sid, "delta", {"content": "a"})

        state = await get_stream_state(sid)
        assert isinstance(state, StreamState)
        assert state.stream_id == sid
        assert state.user_id == "u1"
        assert state.conversation_id == "c1"
        assert state.status == "active"
        assert state.total_seq == 1

    @pytest.mark.asyncio
    async def test_mark_complete(self):
        """测试标记 stream 完成。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await mark_complete(sid)
        state = await get_stream_state(sid)
        assert state.status == "completed"

    @pytest.mark.asyncio
    async def test_delete_stream(self):
        """测试删除 stream。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        await delete_stream(sid)
        with pytest.raises(ValueError, match="not found"):
            await get_stream_state(sid)

    @pytest.mark.asyncio
    async def test_stream_not_found(self):
        """测试操作不存在的 stream。"""
        with pytest.raises(ValueError, match="not found"):
            await get_stream_state("stream:nonexistent")

    @pytest.mark.asyncio
    async def test_append_to_nonexistent(self):
        """测试向不存在的 stream 追加 event。"""
        with pytest.raises(ValueError, match="not found"):
            await append_event("stream:nonexistent", "delta", {"content": "x"})

    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """测试清理过期内存流。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        # 手动设置 created_at 为过去
        _memory_store[sid].created_at = 0

        cleaned = await cleanup_expired(max_age_hours=0)
        assert cleaned == 1
        assert sid not in _memory_store

    @pytest.mark.asyncio
    async def test_event_size_limit(self):
        """测试 event 大小限制。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        # 创建超大 event
        big_data = "x" * (64 * 1024 + 1)
        with pytest.raises(ValueError, match="too large"):
            await append_event(sid, "delta", {"content": big_data})


# ---------------------------------------------------------------------------
# SSE 事件格式
# ---------------------------------------------------------------------------

class TestSSEFormat:
    """SSE 事件格式测试。"""

    def test_sse_event_basic(self):
        """测试基本 SSE 事件格式。"""
        result = sse_event({"type": "delta", "content": "hello"})
        assert 'data: {"type": "delta", "content": "hello"}' in result
        assert result.endswith("\n\n")

    def test_sse_event_with_id(self):
        """测试带 id 的 SSE 事件。"""
        result = sse_event({"type": "delta"}, event_id=42)
        assert "id: 42" in result

    def test_sse_event_with_type(self):
        """测试带 event type 的 SSE 事件。"""
        result = sse_event({"type": "complete"}, event="complete")
        assert "event: complete" in result

    def test_sse_end_event(self):
        """测试结束事件。"""
        result = sse_end_event()
        assert "event: end" in result
        assert '"done":true' in result

    def test_sse_error_event(self):
        """测试错误事件。"""
        result = sse_error_event("something broke")
        assert "event: error" in result
        assert "something broke" in result


# ---------------------------------------------------------------------------
# create_resumable_stream（内存降级模式）
# ---------------------------------------------------------------------------

class TestCreateResumableStream:
    """create_resumable_stream 测试（Redis 不可用 → 内存降级）。"""

    @pytest.mark.asyncio
    async def test_basic_stream(self):
        """测试基本流式输出。"""
        async def source():
            yield {"type": "delta", "content": "hello"}
            yield {"type": "delta", "content": " world"}

        chunks = []
        async for chunk in create_resumable_stream(
            user_id="u1",
            conversation_id="c1",
            source=source(),
        ):
            chunks.append(chunk)

        # 应该有：delta + delta + end
        assert len(chunks) >= 2
        # 最后一个应该是 end event
        assert '"done":true' in chunks[-1]

    @pytest.mark.asyncio
    async def test_stream_meta_event(self):
        """Redis 不可用时不发送 stream_meta 事件。"""
        async def source():
            yield {"type": "delta", "content": "hi"}

        chunks = []
        async for chunk in create_resumable_stream(
            user_id="u1",
            conversation_id="c1",
            source=source(),
        ):
            chunks.append(chunk)

        # Redis 不可用 → 没有 stream_meta 事件
        has_meta = any("stream_meta" in c for c in chunks)
        assert not has_meta

    @pytest.mark.asyncio
    async def test_source_error_handling(self):
        """测试 source 抛异常时输出 error event。"""
        async def source():
            yield {"type": "delta", "content": "start"}
            raise RuntimeError("source broke")

        chunks = []
        async for chunk in create_resumable_stream(
            user_id="u1",
            conversation_id="c1",
            source=source(),
        ):
            chunks.append(chunk)

        # 应该有：delta + error
        assert len(chunks) >= 2
        error_chunk = chunks[-1]
        assert "error" in error_chunk


# ---------------------------------------------------------------------------
# resume_stream
# ---------------------------------------------------------------------------

class TestResumeStream:
    """resume_stream 续传测试。"""

    @pytest.mark.asyncio
    async def test_resume_basic(self):
        """测试基本续传。"""
        # 创建 stream 并追加 events
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id
        await append_event(sid, "delta", {"content": "a"})
        await append_event(sid, "delta", {"content": "b"})

        # 续传：从 seq=1 开始
        chunks = []
        async for chunk in resume_stream(
            stream_id=sid,
            last_seq=1,
            user_id="u1",
        ):
            chunks.append(chunk)

        # 应该有：1 个 delta event + end
        assert len(chunks) == 2
        assert '"content": "b"' in chunks[0]
        assert '"done":true' in chunks[-1]

    @pytest.mark.asyncio
    async def test_resume_not_found(self):
        """测试续传不存在的 stream。"""
        with pytest.raises(StreamNotFoundError):
            async for _ in resume_stream(
                stream_id="stream:nonexistent",
                last_seq=0,
                user_id="u1",
            ):
                pass

    @pytest.mark.asyncio
    async def test_resume_idor_protection(self):
        """测试 IDOR 防护（不同用户不能续传他人 stream）。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id

        with pytest.raises(StreamForbiddenError):
            async for _ in resume_stream(
                stream_id=sid,
                last_seq=0,
                user_id="u2",  # 不同用户
            ):
                pass

    @pytest.mark.asyncio
    async def test_resume_seq_exceeds(self):
        """测试 last_seq 超过 total_seq 时抛出 BadRequest。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id
        await append_event(sid, "delta", {"content": "a"})

        with pytest.raises(StreamBadRequestError):
            async for _ in resume_stream(
                stream_id=sid,
                last_seq=100,
                user_id="u1",
            ):
                pass

    @pytest.mark.asyncio
    async def test_resume_completed_stream(self):
        """测试续传已完成的 stream。"""
        result = await create_stream(user_id="u1", conversation_id="c1")
        sid = result.stream_id
        await append_event(sid, "delta", {"content": "a"})
        await append_event(sid, "complete", {"done": True})
        await mark_complete(sid)

        chunks = []
        async for chunk in resume_stream(
            stream_id=sid,
            last_seq=0,
            user_id="u1",
        ):
            chunks.append(chunk)

        # 2 events + end
        assert len(chunks) == 3
