"""ChromaDB 连接管理（单例模式）.

使用 HTTP 客户端连接现有的 ChromaDB 实例，
复用 Node.js 版已创建的向量数据。

⚠️ 重要：chromadb 的 Python 客户端是【同步】的（底层用 requests），
且默认【没有超时】。如果在 asyncio 事件循环上直接调用
（如 client.get_collection / col.count / client.get_version / collection.query），
一旦 Chroma 服务不可达，同步 recv 会永久阻塞事件循环，
导致【所有】接口（含 /health、/openapi、/commute/optimal）全部卡死转圈。

因此本模块统一通过 ``run_sync`` 把同步调用丢到线程池，并加硬超时，
保证即使 Chroma 挂了也只影响该请求（快速降级），绝不阻塞事件循环。
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Chroma 在本环境经常不可用；任何同步调用最多阻塞这么久就必须放弃，
# 避免拖垮事件循环。
_CHROMA_TIMEOUT_S = 5.0

# 熔断器：一旦探测/连接失败，进入冷却期，期间直接快速失败（不再每次都等 5s），
# 冷却结束后（_CHROMA_DOWN_TTL 秒）再尝试一次，便于 Chroma 恢复后自动复活。
_CHROMA_DOWN_UNTIL: float = 0.0
_CHROMA_DOWN_TTL: float = 60.0
_client_lock: Optional[asyncio.Lock] = None

# 全局单例
_client: Optional[chromadb.HttpClient] = None
_spots_collection: Optional[chromadb.Collection] = None
_spot_docs_collection: Optional[chromadb.Collection] = None


def _parse_chroma_addr() -> tuple[str, int]:
    """解析 CHROMA_URL (格式: http://localhost:8000) → (host, port)。"""
    chroma_url = settings.chroma_url or "http://localhost:8001"
    if "://" in chroma_url:
        _protocol, rest = chroma_url.split("://", 1)
    else:
        _protocol, rest = "http", chroma_url
    if ":" in rest:
        host, port_str = rest.split(":", 1)
        port = int(port_str)
    else:
        host, port = rest, 8001
    return host, port


def _build_client() -> chromadb.HttpClient:
    """【同步】构造 ChromaDB HTTP 客户端。

    ⚠️ 警告：chromadb 1.5.x 的 ``HttpClient`` 构造时会发起一次同步网络调用
    （``get_user_identity``，底层 httpx / requests），默认【无超时】且会
    走 HTTP_PROXY 环境变量。若指向不可达地址（如误配成后端自身端口 8000），
    这一步会【永久阻塞调用线程】。

    因此**绝不能在事件循环线程直接调用**，必须由 ``run_sync`` 丢到线程池。
    """
    host, port = _parse_chroma_addr()
    logger.info("初始化 ChromaDB 客户端: %s:%d", host, port)
    return chromadb.HttpClient(
        host=host,
        port=port,
        settings=ChromaSettings(
            allow_reset=False,
            anonymized_telemetry=False,
        ),
    )


async def run_sync(fn, *args, **kwargs) -> Any:
    """在线程池中执行【同步】chromadb 调用，并加硬超时。

    这样即使 Chroma 不可达（同步 recv 挂起），事件循环也不会被卡住：
    ``asyncio.wait_for`` 会在 ``_CHROMA_TIMEOUT_S`` 后取消 await，
    让当前请求快速降级，而其余请求照常服务。

    Raises:
        TimeoutError: 调用超过 ``_CHROMA_TIMEOUT_S`` 仍未返回。
        其余异常原样抛出，由调用方决定降级策略。
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: fn(*args, **kwargs)),
            timeout=_CHROMA_TIMEOUT_S,
        )
    except asyncio.TimeoutError as exc:
        raise TimeoutError(
            f"Chroma 调用超时（{_CHROMA_TIMEOUT_S}s），服务可能不可达"
        ) from exc


async def get_chroma_client() -> chromadb.HttpClient:
    """获取 ChromaDB HTTP 客户端单例（异步、非阻塞）.

    构造 ``chromadb.HttpClient`` 会发起一次【同步】网络调用
    （``get_user_identity``），必须在 ``run_sync`` 的线程池里执行，
    **绝不能**在事件循环线程直接调用，否则会卡死整个事件循环
    （尤其当 CHROMA_URL 误配成后端自身端口时，会形成自死锁）。

    Returns:
        chromadb.HttpClient: ChromaDB HTTP 客户端实例.

    Raises:
        RuntimeError: 冷却期内或连接/构造失败（调用方应据此降级）。
    """
    global _client, _CHROMA_DOWN_UNTIL, _client_lock
    if _client is not None:
        return _client

    # 冷却期内：上次已确认不可用，直接快速失败，避免每个请求都傻等 5s。
    if time.monotonic() < _CHROMA_DOWN_UNTIL:
        raise RuntimeError("ChromaDB 处于冷却期（近期不可用），快速失败")

    # 用锁防止并发请求重复构造
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    async with _client_lock:
        if _client is not None:
            return _client
        if time.monotonic() < _CHROMA_DOWN_UNTIL:
            raise RuntimeError("ChromaDB 处于冷却期（近期不可用），快速失败")
        try:
            # 关键：构造函数的网络调用必须丢到线程池，绝不阻塞事件循环
            _client = await run_sync(_build_client)
        except Exception:
            # 标记冷却，60s 内不再重试，保证接口快速降级
            _CHROMA_DOWN_UNTIL = time.monotonic() + _CHROMA_DOWN_TTL
            logger.warning("ChromaDB 客户端构造失败，进入 %ss 冷却期", _CHROMA_DOWN_TTL)
            raise
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
        client = await get_chroma_client()
        try:
            # 尝试获取现有集合
            _spots_collection = await run_sync(client.get_collection, name="spots")
            logger.info(
                "已连接 ChromaDB 集合: spots (向量数: %d)",
                await run_sync(_spots_collection.count),
            )
        except Exception:
            # 集合不存在，创建新集合
            logger.warning("集合 'spots' 不存在或不可达，尝试创建新集合")
            _spots_collection = await run_sync(
                client.create_collection,
                name="spots",
                metadata={"hnsw:space": "cosine"},
            )
    return _spots_collection


async def get_spot_docs_collection() -> chromadb.Collection:
    """获取文本层向量集合单例（spot_docs）.

    与 spots 集合共享同一 bge-small-zh-v1.5（512 维）embedding，
    但独立成集合以便按 source_type / credibility_score 元数据检索，
    且不与事实层向量混淆。

    Returns:
        chromadb.Collection: 名为 "spot_docs" 的 ChromaDB 集合.

    Raises:
        RuntimeError: 如果集合不存在且无法创建.
    """
    global _spot_docs_collection
    if _spot_docs_collection is None:
        client = await get_chroma_client()
        try:
            _spot_docs_collection = await run_sync(
                client.get_collection, name="spot_docs"
            )
            logger.info(
                "已连接 ChromaDB 集合: spot_docs (向量数: %d)",
                await run_sync(_spot_docs_collection.count),
            )
        except Exception:
            logger.warning("集合 'spot_docs' 不存在或不可达，尝试创建新集合")
            _spot_docs_collection = await run_sync(
                client.create_collection,
                name="spot_docs",
                metadata={"hnsw:space": "cosine"},
            )
    return _spot_docs_collection


async def check_chroma_health() -> bool:
    """检查 ChromaDB 健康状态（非阻塞）.

    Returns:
        bool: 如果 ChromaDB 可访问返回 True，否则返回 False.
    """
    try:
        client = await get_chroma_client()
        # 简单心跳检查：获取版本信息（线程池 + 超时，避免卡死事件循环）
        await run_sync(client.get_version)
        logger.debug("ChromaDB 健康检查通过")
        return True
    except Exception as e:
        logger.warning("ChromaDB 健康检查失败: %s", str(e))
        return False


async def probe_collection(name: str) -> Dict[str, Any]:
    """探测某个 Chroma 集合的真实可用性（非阻塞，供前端展示向量入库状态）.

    即使 Chroma 不可达也只返回 available=False，绝不会阻塞事件循环。

    Returns:
        {"available": bool, "spotDocsCount": int | None}
        （字段名对齐前端既有契约：spot_docs 集合的计数用 spotDocsCount）
    """
    try:
        client = await get_chroma_client()
        col = await run_sync(client.get_collection, name=name)
        count = await run_sync(col.count)
        return {"available": True, "spotDocsCount": count}
    except Exception as e:
        logger.debug("Chroma 集合 %s 探测失败（不可达）: %s", name, str(e))
        return {"available": False, "spotDocsCount": None}


def reset_chroma_client() -> None:
    """重置 ChromaDB 客户端（用于测试）.

    清除全局单例与冷却期，下次调用时会重新初始化。
    """
    global _client, _spots_collection, _spot_docs_collection, _CHROMA_DOWN_UNTIL
    _client = None
    _spots_collection = None
    _spot_docs_collection = None
    _CHROMA_DOWN_UNTIL = 0.0
    logger.debug("ChromaDB 客户端已重置")
