"""RRF (Reciprocal Rank Fusion) 融合算法.

将多个召回路径的结果进行融合排序，
通过倒数排名加权的方式综合各路径的排序信息。
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# RRF 公式中的常数 k（默认 60，与 TREC 标准一致）
RRF_K = 60


def rrf_merge(
    results_list: List[List[Dict[str, any]]],
    k: int = RRF_K,
    id_key: str = "id",
) -> List[Dict[str, any]]:
    """RRF 融合多个召回路径的结果.

    公式: RRF(d) = Σ (1 / (k + rank_i(d)))
    其中 rank_i(d) 是文档 d 在第 i 个路径中的排名（从 0 开始）。

    Args:
        results_list: 多个召回路径的结果列表，每个路径的结果是一个列表，
            列表中的每个元素是一个字典，必须包含 id_key 字段作为文档唯一标识。
            示例:
                [
                    [{"id": "1", "name": "故宫"}, {"id": "2", "name": "长城"}],
                    [{"id": "2", "name": "长城"}, {"id": "3", "name": "天安门"}],
                ]
        k: RRF 公式中的常数（默认 60）.
        id_key: 文档唯一标识的字段名（默认 "id"）.

    Returns:
        List[Dict[str, any]]: 融合排序后的结果列表，每个元素包含:
            - 原始文档的所有字段
            - '_rrf_score': RRF 融合分数（越高表示排名越靠前）

    Example:
        >>> path1 = [{"id": "1", "name": "故宫"}, {"id": "2", "name": "长城"}]
        >>> path2 = [{"id": "2", "name": "长城"}, {"id": "3", "name": "天安门"}]
        >>> merged = rrf_merge([path1, path2])
        >>> merged[0]['id']
        '2'
        >>> 'rrf_score' in merged[0]
        True
    """
    if not results_list:
        return []

    # 过滤空路径
    valid_paths = [path for path in results_list if path]
    if not valid_paths:
        return []

    # 计算每个文档的 RRF 分数
    # score_map: {doc_id: {"doc": doc, "score": rrf_score}}
    score_map: Dict[str, Dict[str, Any]] = {}

    for path_idx, path in enumerate(valid_paths):
        for rank, doc in enumerate(path):
            doc_id = str(doc.get(id_key))
            if doc_id is None:
                logger.warning("文档缺少 id 字段: %s", doc)
                continue

            rrf_contribution = 1.0 / (k + rank)

            if doc_id in score_map:
                score_map[doc_id]["score"] += rrf_contribution
            else:
                # 深拷贝文档（避免修改原始数据）
                import copy
                doc_copy = copy.deepcopy(doc)
                score_map[doc_id] = {
                    "doc": doc_copy,
                    "score": rrf_contribution,
                }

    # 按 RRF 分数降序排序
    sorted_items = sorted(
        score_map.values(),
        key=lambda x: x["score"],
        reverse=True,
    )

    # 组装最终结果
    merged_results = []
    for i, item in enumerate(sorted_items):
        doc = item["doc"]
        doc["_rrf_score"] = item["score"]
        merged_results.append(doc)

    logger.debug(
        "RRF 融合完成: %d 个路径 -> %d 个文档",
        len(valid_paths),
        len(merged_results),
    )
    return merged_results


def rrf_merge_with_weights(
    results_list: List[List[Dict[str, any]]],
    weights: List[float],
    k: int = RRF_K,
    id_key: str = "id",
) -> List[Dict[str, any]]:
    """带权重的 RRF 融合.

    为不同召回路径分配不同权重，适用于某些路径更可信的场景。
    例如：向量检索权重高，关键词检索权重低。

    Args:
        results_list: 多个召回路径的结果列表.
        weights: 每个路径的权重列表，长度必须与 results_list 一致.
        k: RRF 公式中的常数.
        id_key: 文档唯一标识的字段名.

    Returns:
        List[Dict[str, any]]: 融合排序后的结果列表.

    Raises:
        ValueError: 如果 results_list 和 weights 长度不一致.
    """
    if len(results_list) != len(weights):
        raise ValueError(
            f"results_list 和 weights 长度不一致: "
            f"{len(results_list)} vs {len(weights)}"
        )

    if not results_list:
        return []

    # 过滤空路径
    valid_paths = []
    valid_weights = []
    for path, weight in zip(results_list, weights):
        if path:
            valid_paths.append(path)
            valid_weights.append(weight)

    if not valid_paths:
        return []

    # 计算每个文档的加权 RRF 分数
    score_map: Dict[str, Dict[str, Any]] = {}

    for path_idx, (path, weight) in enumerate(zip(valid_paths, valid_weights)):
        for rank, doc in enumerate(path):
            doc_id = str(doc.get(id_key))
            if doc_id is None:
                continue

            rrf_contribution = weight / (k + rank)

            if doc_id in score_map:
                score_map[doc_id]["score"] += rrf_contribution
            else:
                import copy
                doc_copy = copy.deepcopy(doc)
                score_map[doc_id] = {
                    "doc": doc_copy,
                    "score": rrf_contribution,
                }

    # 排序
    sorted_items = sorted(
        score_map.values(),
        key=lambda x: x["score"],
        reverse=True,
    )

    # 组装结果
    merged_results = []
    for item in sorted_items:
        doc = item["doc"]
        doc["_rrf_score"] = item["score"]
        merged_results.append(doc)

    return merged_results


def merge_and_dedup(
    results_list: List[List[Dict[str, any]]],
    id_key: str = "id",
) -> List[Dict[str, any]]:
    """简单合并多个结果列表并去重（不使用权重）.

    适用于只需要简单合并、不需要精细排序的场景。

    Args:
        results_list: 多个结果列表.
        id_key: 文档唯一标识的字段名.

    Returns:
        List[Dict[str, any]]: 合并去重后的结果列表，保持首次出现的顺序。
    """
    seen = set()
    merged = []
    for path in results_list:
        for doc in path:
            doc_id = str(doc.get(id_key))
            if doc_id and doc_id not in seen:
                seen.add(doc_id)
                merged.append(doc)
    return merged
