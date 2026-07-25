"""RAG 检索引擎模块.

提供三路并行召回、RRF 融合、Cross-Encoder 重排等能力。
"""

from src.services.rag.chroma_client import (
    get_chroma_client,
    get_spots_collection,
    get_spot_docs_collection,
    check_chroma_health,
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
    # ChromaDB 客户端
    "get_chroma_client",
    "get_spots_collection",
    "get_spot_docs_collection",
    "check_chroma_health",
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
