"""
检索质量指标计算。

Hit@K: 正确结果是否在 Top-K 内
MRR (Mean Reciprocal Rank): 正确结果排名的倒数平均值
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class QueryResult:
    """单条 query 的评估结果"""
    query: str
    gold_spot_id: int
    gold_spot_name: str
    gold_city: str
    rank: Optional[int]          # 正确结果的排名（未命中 = None）
    hit_at_k: dict[int, bool]    # {k: is_hit}
    normalized_rank: float       # 1/rank（未命中 = 0.0）
    retrieved_names: list[str]   # Top-K 被检出的名称
    retrieved_ids: list[int]     # Top-K 被检出的 ID


@dataclass
class RetrievalReport:
    """检索评估报告"""
    title: str = "RAG Retrieval Evaluation Report"
    timestamp: str = ""
    dataset_size: int = 0
    k_values: list[int] = field(default_factory=lambda: [1, 3, 5, 10, 20])
    hit_rates: dict[int, float] = field(default_factory=dict)
    mrr: float = 0.0
    per_query: list[QueryResult] = field(default_factory=list)
    by_city: dict[str, float] = field(default_factory=dict)
    by_category: dict[str, float] = field(default_factory=dict)
    by_query_type: dict[str, float] = field(default_factory=dict)
    worst_queries: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def calc_hit_at_k(ranked_ids: list[int], gold_id: int, k: int) -> bool:
    """判断正确结果是否在 Top-K 内。

    Args:
        ranked_ids: 检索结果 ID 列表（按相关性降序）
        gold_id: 正确结果的 ID
        k: Top-K 的 K 值

    Returns:
        True 如果 gold_id 在 ranked_ids[:k] 中
    """
    return gold_id in ranked_ids[:k]


def calc_mrr_for_query(ranked_ids: list[int], gold_id: int) -> float:
    """计算单条 query 的 Reciprocal Rank。

    Args:
        ranked_ids: 检索结果 ID 列表（按相关性降序）
        gold_id: 正确结果的 ID

    Returns:
        1/rank（未命中返回 0.0）
    """
    try:
        rank = ranked_ids.index(gold_id) + 1
        return 1.0 / rank
    except ValueError:
        return 0.0


def find_rank(ranked_ids: list[int], gold_id: int) -> Optional[int]:
    """查找正确结果的排名（1-based）。

    Returns:
        排名（1-indexed），未命中返回 None
    """
    try:
        return ranked_ids.index(gold_id) + 1
    except ValueError:
        return None


def evaluate_retrieval(
    query_ids: list[int],           # 每个 query 对应的正确 spot_id
    ranked_lists: list[list[int]],  # 每个 query 的检索结果 ID 列表
    spot_id_to_name: dict[int, str],
    k_values: Optional[list[int]] = None,
) -> RetrievalReport:
    """执行完整检索评估。

    Args:
        query_ids: 每个 query 对应的正确 spot_id（长度=N）
        ranked_lists: 每个 query 的检索结果 ID 列表（长度=N）
        spot_id_to_name: id -> name 映射
        k_values: 要计算的 K 值列表，默认 [1, 3, 5, 10, 20]

    Returns:
        RetrievalReport 包含所有聚合指标和逐 query 详情
    """
    if k_values is None:
        k_values = [1, 3, 5, 10, 20]

    n = len(query_ids)
    if n == 0:
        return RetrievalReport(dataset_size=0, k_values=k_values)

    per_query: list[QueryResult] = []
    total_rr = 0.0
    miss_count = 0

    for i in range(n):
        gold_id = query_ids[i]
        ranked = ranked_lists[i] if i < len(ranked_lists) else []
        rank = find_rank(ranked, gold_id)
        rr = calc_mrr_for_query(ranked, gold_id)

        hits = {}
        for k in k_values:
            hits[k] = calc_hit_at_k(ranked, gold_id, k)

        retrieved_names = [spot_id_to_name.get(sid, f"unknown-{sid}") for sid in ranked[:max(k_values)]]
        retrieved_ids = ranked[:max(k_values)]

        per_query.append(QueryResult(
            query="",  # 由调用方补充
            gold_spot_id=gold_id,
            gold_spot_name=spot_id_to_name.get(gold_id, f"unknown-{gold_id}"),
            gold_city="",
            rank=rank,
            hit_at_k=hits,
            normalized_rank=rr,
            retrieved_names=retrieved_names,
            retrieved_ids=retrieved_ids,
        ))

        total_rr += rr
        if rank is None:
            miss_count += 1

    # 聚合指标
    mrr = total_rr / n if n > 0 else 0.0
    hit_rates = {}
    for k in k_values:
        hits = sum(1 for qr in per_query if qr.hit_at_k.get(k, False))
        hit_rates[k] = round(hits / n, 4)

    # 找出最差的 query（未命中 Top-5 的）
    worst = []
    for i, qr in enumerate(per_query):
        if not qr.hit_at_k.get(5, False):
            worst.append({
                "index": i,
                "rank": qr.rank,
                "gold_spot_name": qr.gold_spot_name,
                "retrieved_at_5": qr.retrieved_ids[:5],
            })

    recommendations = _generate_recommendations(hit_rates, mrr, miss_count, n)

    return RetrievalReport(
        dataset_size=n,
        k_values=k_values,
        hit_rates=hit_rates,
        mrr=round(mrr, 4),
        per_query=per_query,
        worst_queries=worst,
        recommendations=recommendations,
    )


def _generate_recommendations(
    hit_rates: dict[int, float],
    mrr: float,
    miss_count: int,
    total: int,
) -> list[str]:
    """根据指标生成优化建议"""
    recs = []

    hit5 = hit_rates.get(5, 0)
    hit1 = hit_rates.get(1, 0)
    miss_pct = miss_count / total * 100 if total > 0 else 0

    if hit5 < 0.7:
        recs.append(
            f"🔴 Hit@5={hit5:.1%} 低于 70%，检索层存在明显问题。"
            f"建议：更换更强的 Embedding 模型、优化 Chunking 策略、或增加多路召回。"
        )
    elif hit5 < 0.8:
        recs.append(
            f"🟡 Hit@5={hit5:.1%} 处于临界区（70%-80%）。"
            f"建议：尝试优化 Embedding 模型或调整检索参数。"
        )
    else:
        recs.append(
            f"🟢 Hit@5={hit5:.1%} 高于 80%，检索召回表现良好。"
            f"如果答案质量仍有问题，问题可能出在生成层（LLM 幻觉或 Prompt）。"
        )

    if mrr < 0.3:
        recs.append(
            f"🔴 MRR={mrr:.2f} 很低，即使召回了正确内容也排在很后的位置。"
            f"建议：加强 Rerank 模型或调整 RRF 参数。"
        )
    elif mrr < 0.5:
        recs.append(
            f"🟡 MRR={mrr:.2f} 偏低，Rerank 效果不够理想。"
            f"建议：检视 Cross-Encoder 重排模型或增加 Rerank 候选数。"
        )
    else:
        recs.append(
            f"🟢 MRR={mrr:.2f} 良好，正确内容在结果中排序靠前。"
        )

    if miss_pct > 20:
        recs.append(
            f"🔴 {miss_count}/{total}（{miss_pct:.0f}%）的 query 在 Top-20 中完全未命中。"
            f"建议检查这些 query 的数据覆盖：是否缺失对应的景点知识？"
        )

    recs.append(
        f"建议下一轮用更大规模测试集（200+ query）复测，"
        f"并使用 LLM 自动生成更多样化的 query。"
    )

    return recs
