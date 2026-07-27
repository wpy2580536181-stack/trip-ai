"""RAG 检索引擎模块.

提供四路并行召回（pgvector 向量 + PG 全文 + 评分）、RRF 融合、Cross-Encoder 重排等能力。
"""

from src.services.rag.vector_search import (
    vector_search_spots,
    vector_search_spot_docs,
)
from src.services.rag.fulltext_search import (
    fulltext_search_spots,
    fulltext_search_spot_docs,
)
from src.services.rag.embeddings import (
    get_embedder,
    embed_query,
    embed_documents,
)
from src.services.rag.query_rewriter import (
    rewrite_query,
    extract_keywords,
)
from src.services.rag.reranker import (
    get_reranker,
    rerank,
    rerank_with_credibility,
)
from src.services.rag.rrf import (
    rrf_merge,
    rrf_merge_with_weights,
    RRF_K,
)
from src.services.rag.credibility import (
    compute_credibility,
    weight_by_credibility,
    AUTHORITY_DEFAULTS,
)

__all__ = [
    # pgvector 向量检索
    "vector_search_spots",
    "vector_search_spot_docs",
    # PG 全文检索
    "fulltext_search_spots",
    "fulltext_search_spot_docs",
    # Embedding
    "get_embedder",
    "embed_query",
    "embed_documents",
    # 查询改写
    "rewrite_query",
    "extract_keywords",
    # 重排序
    "get_reranker",
    "rerank",
    "rerank_with_credibility",
    # RRF 融合
    "rrf_merge",
    "rrf_merge_with_weights",
    "RRF_K",
    # 可信度
    "compute_credibility",
    "weight_by_credibility",
    "AUTHORITY_DEFAULTS",
]
