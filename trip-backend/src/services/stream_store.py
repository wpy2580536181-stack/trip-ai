"""StreamStore — Redis 存储 SSE 流状态 + events（对齐 Node.js streamStore.ts）

用途：断点续传流式 Agent
客户端断网后用 Last-Event-ID 头请求续传，服务端
从 Redis 读取缺失的 events 重发。

Redis key 设计（streamId 形如 `stream:{uuid}`）：
  {streamId}            HASH   { status, userId, conversationId, createdAt, lastEventAt }
  {streamId}:events     LIST   JSON 化 events，RPUSH 追加（首个 appendEvent 时创建）
  {streamId}:seq        STRING 原子自增 seq 计数器

TTL: 10 分钟（SSE 流临时数据，客户端重连后立即续传）

无 Redis 降级：使用内存 dict 存储（同进程内仍可续传）
"""

import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from src.config.redis_client import get_redis, is_redis_available

logger = logging.getLogger(__name__)

TTL_SECONDS = 600  # 10 分钟
MAX_EVENT_SIZE = 64 * 1024  # 64KB，单 event 上限


# ---------------------------------------------------------------------------
# 数据类型
# ---------------------------------------------------------------------------

@dataclass
class StreamEvent:
    seq: int
    type: str
    data: Any
    created_at: int  # ms timestamp


@dataclass
class StreamState:
    stream_id: str
    user_id: str
    conversation_id: str
    status: str  # "active" | "completed" | "error"
    created_at: int
    last_event_at: int
    total_seq: int


@dataclass
class CreateStreamResult:
    stream_id: str
    seq: int


# ---------------------------------------------------------------------------
# 内存降级存储（Redis 不可用时使用）
# ---------------------------------------------------------------------------

@dataclass
class _InMemoryStream:
    user_id: str
    conversation_id: str
    status: str
    created_at: int
    last_event_at: int
    seq: int = 0
    events: List[str] = field(default_factory=list)


_memory_store: Dict[str, _InMemoryStream] = {}


def _events_key(stream_id: str) -> str:
    return f"{stream_id}:events"


def _seq_key(stream_id: str) -> str:
    return f"{stream_id}:seq"


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

async def create_stream(
    user_id: str,
    conversation_id: str,
) -> CreateStreamResult:
    """创建新 stream，返回 stream_id。

    客户端应将 stream_id 存到本地，断网重连时用 Last-Event-ID 头传给服务端。
    """
    stream_id = f"stream:{uuid.uuid4()}"
    now = int(time.time() * 1000)

    if is_redis_available():
        r = get_redis()
        assert r is not None
        pipe = r.pipeline()
        pipe.hset(stream_id, mapping={
            "userId": user_id,
            "conversationId": conversation_id,
            "status": "active",
            "createdAt": str(now),
            "lastEventAt": str(now),
        })
        pipe.set(_seq_key(stream_id), 0)
        pipe.expire(stream_id, TTL_SECONDS)
        pipe.expire(_seq_key(stream_id), TTL_SECONDS)
        await pipe.execute()

        logger.debug("Stream created (redis): %s user=%s conv=%s", stream_id, user_id, conversation_id)
    else:
        # 内存降级
        _memory_store[stream_id] = _InMemoryStream(
            user_id=user_id,
            conversation_id=conversation_id,
            status="active",
            created_at=now,
            last_event_at=now,
        )
        logger.debug("Stream created (memory): %s user=%s conv=%s", stream_id, user_id, conversation_id)

    return CreateStreamResult(stream_id=stream_id, seq=0)


async def append_event(
    stream_id: str,
    event_type: str,
    event_data: Any,
) -> int:
    """追加 event 到 stream，原子自增 seq。返回 seq。"""
    serialized = json.dumps({"type": event_type, "data": event_data}, ensure_ascii=False)
    if len(serialized) > MAX_EVENT_SIZE:
        raise ValueError(f"Event too large: {len(serialized)} bytes (max {MAX_EVENT_SIZE})")

    now = int(time.time() * 1000)

    if is_redis_available():
        r = get_redis()
        assert r is not None
        # 原子自增 seq
        seq = await r.incr(_seq_key(stream_id))

        full_event = StreamEvent(
            seq=seq,
            type=event_type,
            data=event_data,
            created_at=now,
        )
        event_json = json.dumps(asdict(full_event), ensure_ascii=False)

        pipe = r.pipeline()
        pipe.rpush(_events_key(stream_id), event_json)
        pipe.hset(stream_id, mapping={"lastEventAt": str(now)})
        # 每次追加续期 TTL
        pipe.expire(stream_id, TTL_SECONDS)
        pipe.expire(_events_key(stream_id), TTL_SECONDS)
        pipe.expire(_seq_key(stream_id), TTL_SECONDS)
        await pipe.execute()

        return seq
    else:
        # 内存降级
        stream = _memory_store.get(stream_id)
        if stream is None:
            raise ValueError(f"Stream not found: {stream_id}")
        stream.seq += 1
        seq = stream.seq
        full_event = StreamEvent(
            seq=seq,
            type=event_type,
            data=event_data,
            created_at=now,
        )
        stream.events.append(json.dumps(asdict(full_event), ensure_ascii=False))
        stream.last_event_at = now
        return seq


async def get_events_since(
    stream_id: str,
    last_seq: int,
) -> List[StreamEvent]:
    """获取 seq > last_seq 的所有 events。"""
    if is_redis_available():
        r = get_redis()
        assert r is not None

        state = await get_stream_state(stream_id)

        if last_seq > state.total_seq:
            raise ValueError(
                f"Last-Event-ID {last_seq} exceeds totalSeq {state.total_seq} for stream {stream_id}"
            )
        if last_seq >= state.total_seq:
            return []

        # LRANGE 索引 0-based: last_seq=0 → 要 seq 1..N → LRANGE 0 -1
        raw = await r.lrange(_events_key(stream_id), last_seq, -1)

        events: List[StreamEvent] = []
        for s in raw:
            try:
                d = json.loads(s)
                events.append(StreamEvent(
                    seq=d["seq"],
                    type=d["type"],
                    data=d["data"],
                    created_at=d["created_at"],
                ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("损坏 event 跳过: stream=%s err=%s raw=%s", stream_id, e, s[:100])
        return events
    else:
        # 内存降级
        stream = _memory_store.get(stream_id)
        if stream is None:
            raise ValueError(f"Stream not found: {stream_id}")
        if last_seq > stream.seq:
            raise ValueError(
                f"Last-Event-ID {last_seq} exceeds totalSeq {stream.seq} for stream {stream_id}"
            )
        if last_seq >= stream.seq:
            return []

        events = []
        for s in stream.events[last_seq:]:
            try:
                d = json.loads(s)
                events.append(StreamEvent(
                    seq=d["seq"],
                    type=d["type"],
                    data=d["data"],
                    created_at=d["created_at"],
                ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("损坏 event 跳过 (memory): stream=%s err=%s", stream_id, e)
        return events


async def get_stream_state(stream_id: str) -> StreamState:
    """获取 stream 状态（用于续传检查 + IDOR 防护）。"""
    if is_redis_available():
        r = get_redis()
        assert r is not None

        hash_data = await r.hgetall(stream_id)
        if not hash_data or "userId" not in hash_data:
            raise ValueError(f"Stream not found: {stream_id}")

        seq_str = await r.get(_seq_key(stream_id))
        total_seq = int(seq_str) if seq_str else 0

        return StreamState(
            stream_id=stream_id,
            user_id=hash_data["userId"],
            conversation_id=hash_data["conversationId"],
            status=hash_data.get("status", "active"),
            created_at=int(hash_data.get("createdAt", 0)),
            last_event_at=int(hash_data.get("lastEventAt", 0)),
            total_seq=total_seq,
        )
    else:
        # 内存降级
        stream = _memory_store.get(stream_id)
        if stream is None:
            raise ValueError(f"Stream not found: {stream_id}")
        return StreamState(
            stream_id=stream_id,
            user_id=stream.user_id,
            conversation_id=stream.conversation_id,
            status=stream.status,
            created_at=stream.created_at,
            last_event_at=stream.last_event_at,
            total_seq=stream.seq,
        )


async def mark_complete(stream_id: str) -> None:
    """标记 stream 完成。不删除 events，允许客户端在 TTL 内随时续传。"""
    if is_redis_available():
        r = get_redis()
        assert r is not None
        await r.hset(stream_id, mapping={"status": "completed"})
        logger.debug("Stream marked completed (redis): %s", stream_id)
    else:
        stream = _memory_store.get(stream_id)
        if stream:
            stream.status = "completed"
            logger.debug("Stream marked completed (memory): %s", stream_id)


async def delete_stream(stream_id: str) -> None:
    """删除 stream（清理用）。"""
    if is_redis_available():
        r = get_redis()
        assert r is not None
        pipe = r.pipeline()
        pipe.delete(stream_id)
        pipe.delete(_events_key(stream_id))
        pipe.delete(_seq_key(stream_id))
        await pipe.execute()
        logger.debug("Stream deleted (redis): %s", stream_id)
    else:
        _memory_store.pop(stream_id, None)
        logger.debug("Stream deleted (memory): %s", stream_id)


async def cleanup_expired(max_age_hours: int = 24) -> int:
    """清理过期的内存流（仅内存模式需要；Redis 由 TTL 自动清理）。

    返回清理的数量。
    """
    if is_redis_available():
        # Redis TTL 自动清理，无需手动
        return 0

    now = int(time.time() * 1000)
    max_age_ms = max_age_hours * 3600 * 1000
    expired_keys = [
        sid for sid, s in _memory_store.items()
        if (now - s.created_at) > max_age_ms
    ]
    for sid in expired_keys:
        del _memory_store[sid]

    if expired_keys:
        logger.info("清理过期内存流: %d 个", len(expired_keys))
    return len(expired_keys)
