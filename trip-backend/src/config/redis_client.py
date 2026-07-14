"""Redis 异步客户端（对齐 Node.js trip-server/src/config/redis.ts）

- 使用 redis.asyncio 创建异步 Redis 连接
- 从 settings.redis_url 读取配置
- 无 Redis 时降级为 None（内存模式）
- 提供 get_redis() 全局获取函数
"""

import logging
from typing import Optional

import redis.asyncio as aioredis

from src.config.settings import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[aioredis.Redis] = None
_redis_available: bool = False


async def init_redis() -> None:
    """应用启动时初始化 Redis 连接。

    连接失败时 _redis_client 保持 None，应用仍可运行（降级模式）。
    """
    global _redis_client, _redis_available

    if not settings.redis_url:
        logger.info("[Redis] redis_url 未配置，使用内存降级模式")
        return

    try:
        _redis_client = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        # 验证连接
        await _redis_client.ping()
        _redis_available = True
        logger.info("[Redis] 连接成功: %s", settings.redis_url)
    except Exception as e:
        logger.warning("[Redis] 连接失败，降级为内存模式: %s", e)
        _redis_client = None
        _redis_available = False


async def close_redis() -> None:
    """应用关闭时释放 Redis 连接。"""
    global _redis_client, _redis_available
    if _redis_client:
        try:
            await _redis_client.close()
        except Exception as e:
            logger.warning("[Redis] 关闭连接失败: %s", e)
    _redis_client = None
    _redis_available = False


def get_redis() -> Optional[aioredis.Redis]:
    """获取 Redis 客户端实例。不可用时返回 None。"""
    return _redis_client if _redis_available else None


def is_redis_available() -> bool:
    """检查 Redis 是否可用。"""
    return _redis_available
