"""Cross-Encoder 重排序模块（单例模式）.

使用 sentence-transformers 的 BGE-reranker-base 模型，
对候选文档进行精细重排序。
"""

import logging
import asyncio
from typing import List, Dict, Optional

import torch

logger = logging.getLogger(__name__)

# 全局单例
_reranker: Optional["CrossEncoder"] = None
_model_name = "BAAI/bge-reranker-base"


def get_reranker() -> "CrossEncoder":
    """获取 CrossEncoder 重排序模型单例.

    Returns:
        CrossEncoder: BGE-reranker-base 模型实例.

    Note:
        首次调用时会下载模型（约 400MB），后续调用直接返回缓存。
    """
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder

            logger.info("加载 Reranker 模型: %s", _model_name)
            _reranker = CrossEncoder(_model_name, device="cpu")
            _reranker.model.eval()  # 推理模式
            logger.info("Reranker 模型加载完成")
        except ImportError:
            logger.error(
                "sentence-transformers 未安装，请执行: "
                "pip install sentence-transformers"
            )
            raise
    return _reranker


def rerank(
    query: str,
    documents: List[str],
    top_k: Optional[int] = None,
) -> List[Dict[str, any]]:
    """对候选文档进行重排序.

    使用 Cross-Encoder 计算查询-文档对的真实相关性分数，
    比向量检索的余弦相似度更精确。

    Args:
        query: 查询文本.
        documents: 候选文档列表（每个文档是一个字符串）.
        top_k: 返回 top-k 个结果，如果为 None 则返回全部。

    Returns:
        List[Dict[str, any]]: 重排序后的文档列表，每个元素包含:
            - 'text': 文档原文
            - 'score': 相关性分数（经过 sigmoid 归一化到 0-1）
            - 'rank': 重排后的排名（从 0 开始）

    Example:
        >>> results = rerank("北京故宫", ["故宫", "长城", "天安门"])
        >>> results[0]['text']
        '故宫'
        >>> results[0]['score'] > results[1]['score']
        True
    """
    if not documents:
        return []

    model = get_reranker()

    # 构造查询-文档对
    pairs = [[query, doc] for doc in documents]

    # 批量预测（Cross-Encoder 直接输出相关性分数）
    try:
        scores = model.predict(pairs, show_progress_bar=False)
        # 将 numpy array 转换为 list
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
    except Exception as e:
        logger.error("Reranker 预测失败: %s", str(e))
        # 降级：返回原始顺序，分数全为 0
        return [
            {"text": doc, "score": 0.0, "rank": i}
            for i, doc in enumerate(documents)
        ]

    # 将分数通过 sigmoid 归一化到 (0, 1)
    # Cross-Encoder 的原始输出可能是任意实数值
    if isinstance(scores, list) and len(scores) > 0:
        scores_tensor = torch.tensor(scores)
        normalized_scores = torch.sigmoid(scores_tensor).tolist()
    else:
        normalized_scores = scores

    # 组装结果并按分数降序排序
    scored_docs = [
        {"text": doc, "score": float(score), "rank": 0}
        for doc, score in zip(documents, normalized_scores)
    ]
    scored_docs.sort(key=lambda x: x["score"], reverse=True)

    # 更新排名
    for i, doc in enumerate(scored_docs):
        doc["rank"] = i

    # 返回 top-k
    if top_k is not None and top_k < len(scored_docs):
        return scored_docs[:top_k]
    return scored_docs


async def rerank_async(
    query: str,
    documents: List[str],
    top_k: Optional[int] = None,
) -> List[Dict[str, any]]:
    """异步对候选文档进行重排序.

    在线程池中运行同步 rerank，避免阻塞事件循环。

    Args:
        query: 查询文本.
        documents: 候选文档列表.
        top_k: 返回 top-k 个结果.

    Returns:
        List[Dict[str, any]]: 重排序后的文档列表.
    """
    return await asyncio.to_thread(rerank, query, documents, top_k)


def batch_rerank(
    queries: List[str],
    document_sets: List[List[str]],
    top_k: Optional[int] = None,
) -> List[List[Dict[str, any]]]:
    """批量重排序（多个查询）.

    Args:
        queries: 查询文本列表.
        document_sets: 每个查询对应的候选文档列表.
        top_k: 每个查询返回 top-k 个结果.

    Returns:
        List[List[Dict[str, any]]]: 每个查询的重排序结果.

    Raises:
        ValueError: 如果 queries 和 document_sets 长度不一致.
    """
    if len(queries) != len(document_sets):
        raise ValueError(
            f"queries 和 document_sets 长度不一致: "
            f"{len(queries)} vs {len(document_sets)}"
        )

    results = []
    for query, docs in zip(queries, document_sets):
        results.append(rerank(query, docs, top_k))
    return results


def reset_reranker() -> None:
    """重置 Reranker 模型（用于测试）.

    清除全局单例，下次调用时会重新加载。
    """
    global _reranker
    _reranker = None
    logger.debug("Reranker 模型已重置")
