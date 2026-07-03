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
        get_chroma_client,
        get_spots_collection,
        check_chroma_health,
        get_embedder,
        embed_query,
        embed_documents,
        rewrite_query,
        extract_keywords,
        rerank,
        rrf_merge,
    )
    __all__.extend([
        "get_chroma_client",
        "get_spots_collection",
        "check_chroma_health",
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
