"""可信度评分（元信息层）.

为每条文本层文档（SpotDoc）计算 5 维可信度：
    authority / freshness / agreement / citation / evidence
并合成综合 credibility_score，用于在 RRF 融合与 Cross-Encoder 重排阶段
对"权威源"加权。

公式（见 docs/rag-data-sources-and-credibility.md §6.1）：
    credibility_score = 0.35*authority + 0.20*freshness
                       + 0.20*agreement + 0.15*citation + 0.10*evidence

所有分数归一化到 [0,1]，写入时算好，检索时直接读取，避免实时计算开销。
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# source_type -> 权威度默认值（authority）
AUTHORITY_DEFAULTS: Dict[str, float] = {
    "wiki": 1.0,
    "wikidata": 1.0,
    "official_gov": 1.0,
    "official_scenic": 0.9,
    "gaode_detail": 0.85,
    "api_partner": 0.8,
    "osm": 0.85,
    "geonames": 0.85,
    "academic": 0.95,
    "ugc_authorized": 0.6,
    "ugc_public": 0.5,
    "llm_generated": 0.4,
    "realtime_mcp": 0.8,
}

# 5 维权重
WEIGHTS: Dict[str, float] = {
    "authority": 0.35,
    "freshness": 0.20,
    "agreement": 0.20,
    "citation": 0.15,
    "evidence": 0.10,
}

# 引用数归一化分母（维基 backlinks / 学术 citations 映射到 [0,1]）
CITATION_NORM_DENOMINATOR = 50.0

# 新鲜度：发布距今 ≤30 天视为 1.0；超过按线性衰减到 0
FRESHNESS_FULL_DAYS = 30
FRESHNESS_ZERO_DAYS = 365


def _freshness_from_date(published_at: Optional[datetime], now: Optional[datetime] = None) -> float:
    """由发布时间计算新鲜度（0~1）."""
    if published_at is None:
        return 0.5
    now = now or datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    days = (now - published_at).days
    if days <= FRESHNESS_FULL_DAYS:
        return 1.0
    if days >= FRESHNESS_ZERO_DAYS:
        return 0.0
    return round(1.0 - (days - FRESHNESS_FULL_DAYS) / (FRESHNESS_ZERO_DAYS - FRESHNESS_FULL_DAYS), 4)


def compute_credibility(
    source_type: str,
    *,
    freshness: Optional[float] = None,
    agreement: Optional[float] = None,
    citation_count: int = 0,
    evidence_density: Optional[float] = None,
    published_at: Optional[datetime] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """计算单条文本层的 5 维可信度与综合分.

    Args:
        source_type: 来源类型（见 AUTHORITY_DEFAULTS 键）。
        freshness: 显式新鲜度（0~1）；缺省由 published_at 推算，再缺省 0.5。
        agreement: 多源一致度（0~1）；缺省 0.0（单源）。
        citation_count: 引用/反向链接数（整数）；归一化到 [0,1]。
        evidence_density: 证据密度（0~1）；缺省 0.0。
        published_at: 原文发布时间。
        now: 当前时间（测试可注入）。

    Returns:
        {
            "authority_score", "freshness_score", "agreement_score",
            "citation_count", "evidence_density", "credibility_score"
        }
    """
    authority = float(AUTHORITY_DEFAULTS.get(source_type, 0.5))
    if freshness is None:
        freshness = _freshness_from_date(published_at, now)
    if agreement is None:
        agreement = 0.0
    if evidence_density is None:
        evidence_density = 0.0
    citation_norm = min(float(citation_count) / CITATION_NORM_DENOMINATOR, 1.0) if citation_count else 0.0

    score = (
        WEIGHTS["authority"] * authority
        + WEIGHTS["freshness"] * freshness
        + WEIGHTS["agreement"] * agreement
        + WEIGHTS["citation"] * citation_norm
        + WEIGHTS["evidence"] * evidence_density
    )
    return {
        "authority_score": round(authority, 4),
        "freshness_score": round(float(freshness), 4),
        "agreement_score": round(float(agreement), 4),
        "citation_count": int(citation_count),
        "evidence_density": round(float(evidence_density), 4),
        "credibility_score": round(float(score), 4),
    }


def weight_by_credibility(rrf_contribution: float, doc: Dict[str, Any]) -> float:
    """RRF 融合阶段的权重调节器：用可信度放大/缩小单路贡献.

    综合分 cred ∈ [0,1] → 乘数 (0.5 + cred) ∈ [0.5, 1.5]。
    权威源（wiki=1.0 → 乘数 1.5）比 LLM 生成（0.4 → 0.9）获得更高排序权重。

    Args:
        rrf_contribution: rrf_merge_with_weights 计算出的原始贡献 weight/(k+rank)。
        doc: 候选文档（需含 credibility_score 字段，缺省 0.5）。

    Returns:
        调节后的贡献值。
    """
    cred = doc.get("credibility_score", 0.5)
    try:
        cred = float(cred)
    except (TypeError, ValueError):
        cred = 0.5
    return rrf_contribution * (0.5 + cred)
