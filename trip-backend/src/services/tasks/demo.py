"""Demo 任务 —— 用于验证 arq 接入。

M0 阶段：3 个最小可用任务
- demo_echo: 回显（验证基础入队/消费）
- demo_write_redis: 写 Redis（验证 worker 能用项目 redis_client）
- demo_raise: 故意抛错（验证失败重试/死信）

实际生产任务（M1/M2 阶段）会替换为：
- sync_spot_to_chroma: API 写路径异步 embedding 同步
- post_chat_summary: chat 后处理摘要压缩
- fetch_wiki_for_spot: 维基抓取
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    """UTC 时间 ISO8601 字符串（带 Z 后缀，跨时区可读）。"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


async def demo_echo(ctx: dict, message: str) -> dict:
    """回显任务：最基础的 demo，验证入队/消费链路。

    Args:
        ctx: arq 注入的上下文（含 job_id / 尝试次数等）
        message: 任意字符串

    Returns:
        {"echoed": message, "job_id": ..., "attempt": ..., "ts": ...}
    """
    result = {
        "echoed": message,
        "job_id": ctx.get("job_id"),
        "attempt": ctx.get("job_try"),
        "ts": _utcnow_iso(),
    }
    logger.info("[demo_echo] %s", result)
    return result


async def demo_write_redis(ctx: dict, key: str, value: str) -> dict:
    """写 Redis 任务：验证 worker 能复用项目 redis_client。

    Args:
        ctx: arq 上下文
        key: Redis key
        value: 要写入的值

    Returns:
        {"key": key, "value": value, "written_at": ...}
    """
    from src.config.redis_client import get_redis

    r = get_redis()
    if r is None:
        raise RuntimeError("Redis 不可用，demo_write_redis 需要 Redis")
    await r.setex(key, 60, value)  # 60s TTL
    logger.info("[demo_write_redis] wrote key=%s value=%s", key, value)
    return {"key": key, "value": value, "written_at": _utcnow_iso()}


async def demo_raise(ctx: dict, should_fail: bool = True) -> dict:
    """故意抛错任务：用于测试 arq 失败重试 / 死信。

    Args:
        ctx: arq 上下文
        should_fail: True 时抛错（验证重试），False 时正常返回
    """
    attempt = ctx.get("job_try", 1)
    if should_fail:
        logger.warning("[demo_raise] attempt=%s, 故意抛错", attempt)
        raise ValueError(f"demo_raise attempt={attempt} simulated failure")
    logger.info("[demo_raise] attempt=%s, 正常返回", attempt)
    return {"attempt": attempt, "ok": True}
