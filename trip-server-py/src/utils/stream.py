"""SSE 续传工具（对齐 Node.js trip-server/src/utils/stream.ts）

错误类型：
  - StreamNotFoundError    — stream 不存在或已过期
  - StreamForbiddenError   — stream 不属于当前用户
  - StreamBadRequestError  — 缺少必要的请求头 / lastSeq 超界

模式：
  1. Redis 可用 → 创建 Redis stream + 写 SSE 边写 Redis（双写）
  2. Redis 不可用 → 降级为纯 SSE（不可续传，但不报错）
"""

import json
import logging
from typing import AsyncGenerator, Optional, Any, Dict

from src.config.redis_client import is_redis_available
from src.services import stream_store

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 错误类型（让 controller 用 isinstance 区分响应码）
# ---------------------------------------------------------------------------

class StreamNotFoundError(Exception):
    def __init__(self, stream_id: str):
        super().__init__(f"Stream not found: {stream_id}")
        self.stream_id = stream_id


class StreamForbiddenError(Exception):
    def __init__(self):
        super().__init__("Forbidden: stream belongs to another user")


class StreamBadRequestError(Exception):
    pass


# ---------------------------------------------------------------------------
# SSE 事件格式
# ---------------------------------------------------------------------------

def sse_event(
    data: Dict[str, Any],
    event: Optional[str] = None,
    event_id: Optional[int] = None,
) -> str:
    """构造 SSE 协议字符串。"""
    parts = []
    if event_id is not None:
        parts.append(f"id: {event_id}")
    if event:
        parts.append(f"event: {event}")
    parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
    parts.append("")
    parts.append("")
    return "\n".join(parts)


def sse_end_event() -> str:
    """SSE 结束事件。"""
    return 'event: end\ndata: {"done":true}\n\n'


def sse_error_event(message: str) -> str:
    """SSE 错误事件。"""
    return f"event: error\ndata: {json.dumps({'type': 'error', 'error': message}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 可续传 SSE 流生成器
# ---------------------------------------------------------------------------

async def create_resumable_stream(
    user_id: str,
    conversation_id: str,
    source: AsyncGenerator[Dict[str, Any], None],
) -> AsyncGenerator[str, None]:
    """创建可续传的 SSE 流（async generator）。

    边从 source 读取事件，边：
      1. 写入 SSE 流（yield）
      2. 同步写入 StreamStore（fire-and-forget 语义）

    Args:
        user_id: 当前用户 ID
        conversation_id: 对话 ID
        source: 上游事件生成器，每个元素是 {"type": ..., "data": ...} 字典

    Yields:
        SSE 格式字符串
    """
    stream_id: Optional[str] = None
    local_seq = 0

    # 尝试创建 Redis stream
    if is_redis_available():
        try:
            result = await stream_store.create_stream(user_id, conversation_id)
            stream_id = result.stream_id
        except Exception as e:
            logger.warning("创建 Redis stream 失败，降级为不可续传: %s", e)

    # 发送 stream ID 元数据事件（客户端保存到 localStorage 用于续传）
    if stream_id:
        yield sse_event({"type": "stream_meta", "streamId": stream_id})

    try:
        async for payload in source:
            local_seq += 1
            event_type = payload.get("type", "delta")

            # 写 SSE（带 id 字段，遵循 SSE 协议）
            yield sse_event(payload, event_id=local_seq)

            # 写 StreamStore（best-effort，不阻塞流）
            if stream_id:
                try:
                    await stream_store.append_event(stream_id, event_type, payload)
                except Exception as e:
                    logger.warning("Redis 写 event 失败: stream=%s err=%s", stream_id, e)

        # 正常结束
        yield sse_end_event()
        if stream_id:
            try:
                await stream_store.mark_complete(stream_id)
            except Exception as e:
                logger.warning("mark_complete 失败: stream=%s err=%s", stream_id, e)

    except Exception as e:
        logger.error("SSE 流异常: %s", e)
        yield sse_error_event(str(e))
        if stream_id:
            try:
                await stream_store.mark_complete(stream_id)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# 续传 stream
# ---------------------------------------------------------------------------

async def resume_stream(
    stream_id: str,
    last_seq: int,
    user_id: str,
) -> AsyncGenerator[str, None]:
    """续传 stream：重发 last_seq 之后的所有 events。

    错误类型（controller 用 isinstance 区分响应码）：
      - StreamNotFoundError    → 404
      - StreamForbiddenError   → 403
      - StreamBadRequestError  → 400

    Yields:
        SSE 格式字符串
    """
    # 获取 stream 状态
    try:
        state = await stream_store.get_stream_state(stream_id)
    except ValueError as e:
        if "not found" in str(e).lower():
            raise StreamNotFoundError(stream_id)
        raise

    # IDOR 防护：stream owner 必须匹配当前 user
    if str(state.user_id) != str(user_id):
        logger.warning(
            "IDOR: 用户尝试访问他人 stream: stream=%s owner=%s requester=%s",
            stream_id, state.user_id, user_id,
        )
        raise StreamForbiddenError()

    # 读 events
    try:
        events = await stream_store.get_events_since(stream_id, last_seq)
    except ValueError as e:
        if "exceed" in str(e).lower():
            raise StreamBadRequestError(str(e))
        raise

    # 重发 events
    for ev in events:
        payload = ev.data if isinstance(ev.data, dict) else {"type": ev.type, "data": ev.data}
        yield sse_event(payload, event_id=ev.seq)

    # 写 end
    yield sse_end_event()

    logger.info(
        "续传完成: stream=%s lastSeq=%d count=%d status=%s",
        stream_id, last_seq, len(events), state.status,
    )
