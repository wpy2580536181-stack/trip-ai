"""Embedding 模型管理（单例模式）.

使用 sentence-transformers 的 BGE-small-zh-v1.5 模型，
提供文本向量化能力。
"""

import logging
from typing import List, Optional

import numpy as np

logger = logging.getLogger(__name__)

# 全局单例
_embedder: Optional["SentenceTransformer"] = None
_model_name = "BAAI/bge-small-zh-v1.5"


def get_embedder() -> "SentenceTransformer":
    """获取 SentenceTransformer 单例.

    Returns:
        SentenceTransformer: BGE-small-zh-v1.5 模型实例.

    Note:
        首次调用时会下载模型（约 40MB），后续调用直接返回缓存。
    """
    global _embedder
    if _embedder is None:
        try:
            from sentence_transformers import SentenceTransformer

            logger.info("加载 Embedding 模型: %s", _model_name)
            _embedder = SentenceTransformer(_model_name, device="cpu")
            _embedder.eval()  # 推理模式
            logger.info("Embedding 模型加载完成")
        except ImportError:
            logger.error(
                "sentence-transformers 未安装，请执行: "
                "pip install sentence-transformers"
            )
            raise
    return _embedder


def embed_query(text: str) -> List[float]:
    """将查询文本转换为向量.

    Args:
        text: 查询文本.

    Returns:
        List[float]: 归一化的向量（384 维）。

    Example:
        >>> vec = embed_query("北京故宫")
        >>> len(vec)
        384
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
        List[List[float]]: 归一化的向量列表，每个向量 384 维。

    Example:
        >>> vecs = embed_documents(["北京故宫", "长城"])
        >>> len(vecs)
        2
        >>> len(vecs[0])
        384
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

    Args:
        text: 查询文本.

    Returns:
        List[float]: 归一化的向量（384 维）。
    """
    import asyncio

    return await asyncio.to_thread(embed_query, text)


async def embed_documents_async(texts: List[str]) -> List[List[float]]:
    """异步批量将文档转换为向量.

    Args:
        texts: 文档文本列表.

    Returns:
        List[List[float]]: 归一化的向量列表。
    """
    import asyncio

    return await asyncio.to_thread(embed_documents, texts)


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
