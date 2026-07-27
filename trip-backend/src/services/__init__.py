"""Services 模块初始化.

导出所有业务服务模块。
"""

from src.services.user_service import UserService
from src.services.knowledge_service import KnowledgeService

__all__ = [
    "UserService",
    "KnowledgeService",
]

# RAG 模块（延迟导入，避免循环依赖）
try:
    from src.services.rag import (
        vector_search_spots,
        vector_search_spot_docs,
        fulltext_search_spots,
        fulltext_search_spot_docs,
        get_embedder,
        embed_query,
        embed_documents,
        rewrite_query,
        extract_keywords,
        rerank,
        rrf_merge,
    )
    __all__.extend([
        "vector_search_spots",
        "vector_search_spot_docs",
        "fulltext_search_spots",
        "fulltext_search_spot_docs",
        "get_embedder",
        "embed_query",
        "embed_documents",
        "rewrite_query",
        "extract_keywords",
        "rerank",
        "rrf_merge",
    ])
except ImportError:
    # RAG 模块不可用（例如 sentence-transformers 未安装）
    pass
