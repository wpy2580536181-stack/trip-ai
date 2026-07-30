"""Embedding 模型管理（单例模式）.

使用 sentence-transformers 的 BGE-small-zh-v1.5 模型，
提供文本向量化能力。
"""

import asyncio
import logging
import os
from typing import List, Optional

import numpy as np

# 国内网络环境下 huggingface.co 直连会超时/被拒（模型加载时拉 adapter_config.json 等元数据），
# 默认走 hf-mirror 镜像；如需官方源可显式设置非空 HF_ENDPOINT 覆盖。
if not os.environ.get("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

logger = logging.getLogger(__name__)

# 全局单例
_embedder: Optional["SentenceTransformer"] = None
# 模型加载失败后缓存该状态：避免每次请求都重复慢速下载（如 HF 镜像 502）。
# 一旦置为 True，后续所有 embed 调用直接失败并走降级路径（字面/全文检索），
# 不再阻塞事件循环去重下模型。
_load_failed: bool = False
_model_name = "BAAI/bge-small-zh-v1.5"

# 单次加载/推理的最长耗时（秒）。用于兜底：HF 镜像不可达时会长时间重试 502，
# 用此上限截断，保证首次请求也不会无限期卡死在"查询景点"阶段。
_EMBED_TIMEOUT_S = 40.0


def get_embedder() -> "SentenceTransformer":
    """获取 SentenceTransformer 单例.

    Returns:
        SentenceTransformer: BGE-small-zh-v1.5 模型实例.

    Note:
        首次调用时会下载模型（约 40MB），后续调用直接返回缓存。
        若加载失败（镜像不可达等），会缓存失败状态，后续调用直接抛错，
        由调用方降级到字面/全文检索，避免每请求重复慢速下载。
    """
    global _embedder, _load_failed
    if _embedder is not None:
        return _embedder
    if _load_failed:
        raise RuntimeError("Embedding 模型此前加载失败，已禁用（HF 镜像不可达？）")
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("加载 Embedding 模型: %s", _model_name)
        _embedder = SentenceTransformer(_model_name, device="cpu")
        _embedder.eval()  # 推理模式
        logger.info("Embedding 模型加载完成")
        return _embedder
    except Exception as e:
        _load_failed = True
        logger.error(
            "Embedding 模型加载失败（已缓存失败状态，后续请求直接降级到字面/全文检索）: %s",
            e,
        )
        raise


def embed_query(text: str) -> List[float]:
    """将查询文本转换为向量.

    Args:
        text: 查询文本.

    Returns:
        List[float]: 归一化的向量（512 维）。

    Example:
        >>> vec = embed_query("北京故宫")
        >>> len(vec)
        512
    """
    model = get_embedder()
    # BGE 模型需要在查询前添加前缀（提升检索效果）
    prefixed_text = f"为这个句子生成表示以用于检索相关文章：{text}"
    embedding = model.encode(
        prefixed_text,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return embedding.tolist()


def embed_documents(texts: List[str]) -> List[List[float]]:
    """批量将文档转换为向量.

    Args:
        texts: 文档文本列表.

    Returns:
        List[List[float]]: 归一化的向量列表，每个向量 512 维。

    Example:
        >>> vecs = embed_documents(["北京故宫", "长城"])
        >>> len(vecs)
        2
        >>> len(vecs[0])
        512
    """
    if not texts:
        return []

    model = get_embedder()
    # 文档不需要添加查询前缀
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,  # 批量推理加速
    )
    return embeddings.tolist()


async def embed_query_async(text: str) -> List[float]:
    """异步将查询文本转换为向量.

    在线程池中运行同步 embedding，避免阻塞事件循环。
    单次耗时受 _EMBED_TIMEOUT_S 上限保护：模型加载/推理异常慢（如 HF 镜像
    不可达反复 502）时快速失败，由调用方降级到字面/全文检索，
    避免"查询景点"阶段长时间卡死。

    Args:
        text: 查询文本.

    Returns:
        List[float]: 归一化的向量（512 维）。
    """
    import asyncio

    return await asyncio.wait_for(asyncio.to_thread(embed_query, text), timeout=_EMBED_TIMEOUT_S)


async def embed_documents_async(texts: List[str]) -> List[List[float]]:
    """异步批量将文档转换为向量.

    Args:
        texts: 文档文本列表.

    Returns:
        List[List[float]]: 归一化的向量列表。
    """
    import asyncio

    return await asyncio.wait_for(asyncio.to_thread(embed_documents, texts), timeout=_EMBED_TIMEOUT_S * 2)


def mark_embedder_unavailable() -> None:
    """标记 Embedding 模型为不可用（fail-closed）。

    在 Agent 引擎启动时调用：默认假设模型不可用，所有 embedding 调用立即失败并
    降级到字面/全文检索，避免首个请求卡在模型下载（HF 镜像不可达时尤其明显）。
    后台预热任务成功加载后，再经 load_embedder_force() 重新启用。
    """
    global _load_failed
    _load_failed = True


async def load_embedder_force() -> bool:
    """强制尝试加载 Embedding 模型（绕过 fail-closed 标记）。

    供后台预热任务调用：成功则写入单例并清除失败标记，失败则保持不可用。
    返回是否加载成功。

    单次加载受 _EMBED_TIMEOUT_S 上限保护，不会无限期阻塞。
    """
    global _embedder, _load_failed
    try:
        from sentence_transformers import SentenceTransformer

        logger.info("预热加载 Embedding 模型: %s", _model_name)
        model = await asyncio.wait_for(
            asyncio.to_thread(SentenceTransformer, _model_name, device="cpu"),
            timeout=_EMBED_TIMEOUT_S,
        )
        model.eval()
        _embedder = model
        _load_failed = False
        logger.info("Embedding 模型预热完成，已启用向量检索")
        return True
    except Exception as e:
        _load_failed = True
        logger.warning("Embedding 模型预热失败（保持降级到字面/全文检索）: %s", e)
        return False


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """计算两个向量的余弦相似度.

    Args:
        vec1: 第一个向量.
        vec2: 第二个向量.

    Returns:
        float: 余弦相似度，范围 [-1, 1]。
    """
    v1 = np.array(vec1)
    v2 = np.array(vec2)
    return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))


def reset_embedder() -> None:
    """重置 Embedding 模型（用于测试）.

    清除全局单例，下次调用时会重新加载。
    """
    global _embedder
    _embedder = None
    logger.debug("Embedding 模型已重置")
