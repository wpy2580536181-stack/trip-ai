"""ChromaDB 连接管理（单例模式）.

使用 HTTP 客户端连接现有的 ChromaDB 实例，
复用 Node.js 版已创建的向量数据。
"""

import logging
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import settings

logger = logging.getLogger(__name__)

# 全局单例
_client: Optional[chromadb.HttpClient] = None
_spots_collection: Optional[chromadb.Collection] = None


def get_chroma_client() -> chromadb.HttpClient:
    """获取 ChromaDB HTTP 客户端单例.

    Returns:
        chromadb.HttpClient: ChromaDB HTTP 客户端实例.
    """
    global _client
    if _client is None:
        # 解析 CHROMA_URL (格式: http://localhost:8000)
        chroma_url = settings.chroma_url or "http://localhost:8000"
        # 移除协议前缀，解析主机和端口
        if "://" in chroma_url:
            protocol, rest = chroma_url.split("://", 1)
        else:
            protocol, rest = "http", chroma_url

        if ":" in rest:
            host, port_str = rest.split(":", 1)
            port = int(port_str)
        else:
            host = rest
            port = 8000

        logger.info("初始化 ChromaDB 客户端: %s:%d", host, port)
        _client = chromadb.HttpClient(
            host=host,
            port=port,
            settings=ChromaSettings(
                allow_reset=False,
                anonymized_telemetry=False,
            ),
        )
    return _client


async def get_spots_collection() -> chromadb.Collection:
    """获取景点向量集合单例.

    Returns:
        chromadb.Collection: 名为 "spots" 的 ChromaDB 集合.

    Raises:
        RuntimeError: 如果集合不存在且无法创建.
    """
    global _spots_collection
    if _spots_collection is None:
        client = get_chroma_client()
        try:
            # 尝试获取现有集合
            _spots_collection = client.get_collection(name="spots")
            logger.info(
                "已连接 ChromaDB 集合: spots (向量数: %d)",
                _spots_collection.count(),
            )
        except Exception:
            # 集合不存在，创建新集合
            logger.warning("集合 'spots' 不存在，创建新集合")
            _spots_collection = client.create_collection(
                name="spots",
                metadata={"hnsw:space": "cosine"},
            )
    return _spots_collection


async def check_chroma_health() -> bool:
    """检查 ChromaDB 健康状态.

    Returns:
        bool: 如果 ChromaDB 可访问返回 True，否则返回 False.
    """
    try:
        client = get_chroma_client()
        # 简单心跳检查：获取版本信息
        version = client.get_version()
        logger.debug("ChromaDB 健康检查通过: version=%s", version)
        return True
    except Exception as e:
        logger.warning("ChromaDB 健康检查失败: %s", str(e))
        return False


def reset_chroma_client() -> None:
    """重置 ChromaDB 客户端（用于测试）.

    清除全局单例，下次调用时会重新初始化。
    """
    global _client, _spots_collection
    _client = None
    _spots_collection = None
    logger.debug("ChromaDB 客户端已重置")
