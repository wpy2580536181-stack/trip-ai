"""RAG 检索引擎单元测试.

测试 RAG 模块的各个组件：
- query_rewriter: 查询改写
- rrf: RRF 融合算法
- reranker: Cross-Encoder 重排（需要模型，使用 mock）
- embeddings: Embedding 生成（需要模型，使用 mock）
- chroma_client: ChromaDB 客户端（需要服务，使用 mock）
"""

import sys
import pytest
import asyncio
from typing import List, Dict, Any


def _ensure_real_modules():
    """Ensure torch, chromadb, etc. are real modules in sys.modules.

    test_agent_imports.py mocks these modules via sys.modules.
    If reranker.py or chroma_client.py were first imported while those
    mocks were active, their module-level imports hold mock references.
    Fix: ensure sys.modules has the real modules and remove stale cached modules.
    """
    mock_names = ["torch", "chromadb", "sentence_transformers"]
    from unittest.mock import MagicMock

    changed = False
    for name in mock_names:
        mod = sys.modules.get(name)
        if isinstance(mod, MagicMock):
            # Module is still mocked - remove it so real import can happen
            sys.modules.pop(name, None)
            # Also remove any mock sub-modules (e.g. torch.nn, chromadb.config)
            to_remove = [k for k in sys.modules if k.startswith(name + ".") and isinstance(sys.modules[k], MagicMock)]
            for k in to_remove:
                sys.modules.pop(k, None)
            changed = True

    if changed:
        # Remove cached RAG modules that may have picked up mocks
        # so they get re-imported with real dependencies
        rag_modules = [
            "src.services.rag.reranker",
            "src.services.rag.embeddings",
            "src.services.rag.chroma_client",
        ]
        for mod_name in rag_modules:
            sys.modules.pop(mod_name, None)


# Run module cleanup before any tests
_ensure_real_modules()

# Force-import heavy dependencies at collection time so they are in sys.modules
# before any RAG sub-module is imported (prevents mock contamination from
# test_agent_imports.py).
# Note: torch import may fail if it was already loaded in a conflicting state.
# In that case, we'll skip torch-dependent tests at runtime.
_torch_import_ok = True
try:
    import torch as _torch_preload  # noqa: F401
except Exception:
    _torch_import_ok = False

# Pre-import reranker so it picks up the real torch during collection
# (before test_agent_imports can mock sys.modules)
if _torch_import_ok:
    try:
        import src.services.rag.reranker as _reranker_preload  # noqa: F401
    except Exception:
        pass


class TestQueryRewriter:
    """测试查询改写模块."""

    def test_extract_keywords(self):
        """测试关键词提取."""
        from src.services.rag.query_rewriter import extract_keywords

        # 测试英文/空格分隔的文本（注意：函数会转为小写）
        keywords = extract_keywords("I want to go to Beijing Palace Museum")
        assert "beijing" in keywords
        assert "palace" in keywords

        # 测试停用词过滤
        keywords = extract_keywords("I and you go to Beijing")
        assert "i" not in keywords
        assert "and" not in keywords
        assert "beijing" in keywords

        # 测试空输入
        keywords = extract_keywords("")
        assert len(keywords) == 0

    def test_rewrite_query(self):
        """测试查询改写."""
        from src.services.rag.query_rewriter import rewrite_query

        # 测试基本改写
        result = rewrite_query("我想去北京故宫玩", city="北京")
        assert "北京" in result
        assert "故宫" in result

        # 测试无城市
        result = rewrite_query("我想去故宫玩")
        assert "故宫" in result

        # 测试空查询
        result = rewrite_query("")
        assert result == ""

    def test_detect_city(self):
        """测试城市检测."""
        from src.services.rag.query_rewriter import detect_city

        # 测试直接城市名
        assert detect_city("我想去北京玩") == "北京"
        assert detect_city("上海有什么好玩的") == "上海"

        # 测试模式匹配
        assert detect_city("去成都玩") == "成都"

        # 测试无城市
        assert detect_city("有什么好玩的") is None

    def test_detect_intent(self):
        """测试意图检测."""
        from src.services.rag.query_rewriter import detect_intent

        assert detect_intent("我想去看景点") == "scenic"
        assert detect_intent("北京有什么好吃的") == "food"
        assert detect_intent("住在哪里比较好") == "hotel"
        assert detect_intent("怎么去故宫") == "transport"
        assert detect_intent("随便看看") == "general"


class TestRRF:
    """测试 RRF 融合算法."""

    def test_rrf_merge_basic(self):
        """测试基本 RRF 融合."""
        from src.services.rag.rrf import rrf_merge

        path1 = [
            {"id": "1", "name": "故宫"},
            {"id": "2", "name": "长城"},
        ]
        path2 = [
            {"id": "2", "name": "长城"},
            {"id": "3", "name": "天安门"},
        ]

        result = rrf_merge([path1, path2])

        # 长城在两个路径中都排第一，应该融合后排第一
        assert result[0]["id"] == "2"
        assert "_rrf_score" in result[0]
        assert result[0]["_rrf_score"] > 0

    def test_rrf_merge_empty_paths(self):
        """测试空路径."""
        from src.services.rag.rrf import rrf_merge

        # 全空
        result = rrf_merge([[], []])
        assert len(result) == 0

        # 部分空
        path1 = [{"id": "1", "name": "故宫"}]
        result = rrf_merge([path1, []])
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_rrf_merge_single_path(self):
        """测试单路径."""
        from src.services.rag.rrf import rrf_merge

        path1 = [
            {"id": "1", "name": "故宫"},
            {"id": "2", "name": "长城"},
        ]

        result = rrf_merge([path1])
        assert len(result) == 2
        assert result[0]["id"] == "1"

    def test_rrf_merge_with_weights(self):
        """测试带权重的 RRF 融合."""
        from src.services.rag.rrf import rrf_merge_with_weights

        path1 = [{"id": "1", "name": "故宫"}]
        path2 = [{"id": "2", "name": "长城"}]

        # path1 权重高
        result = rrf_merge_with_weights(
            [path1, path2],
            weights=[2.0, 1.0],
        )
        assert result[0]["id"] == "1"

    def test_rrf_merge_dedup(self):
        """测试去重合并."""
        from src.services.rag.rrf import merge_and_dedup

        path1 = [{"id": "1", "name": "故宫"}, {"id": "2", "name": "长城"}]
        path2 = [{"id": "2", "name": "长城"}, {"id": "3", "name": "天安门"}]

        result = merge_and_dedup([path1, path2])
        assert len(result) == 3  # 去重后 3 个
        assert result[0]["id"] == "1"  # 保持顺序


class TestRerankerMock:
    """测试重排序模块（使用 mock）."""

    def test_rerank_mock(self, monkeypatch):
        """测试重排序（mock 模型）."""
        import numpy as np
        from src.services.rag.reranker import rerank, reset_reranker
        import src.services.rag.reranker as _reranker_mod

        # Get real torch from reranker module's namespace
        # (it was imported correctly when reranker was first loaded)
        _torch = _reranker_mod.torch

        # Mock CrossEncoder
        class MockCrossEncoder:
            def predict(self, pairs, **kwargs):
                # 模拟分数：第一个文档分数最高
                return np.array([2.5, 1.0, 0.5])

        monkeypatch.setattr(
            "src.services.rag.reranker._reranker",
            MockCrossEncoder(),
        )

        query = "北京故宫"
        documents = ["故宫是皇家宫殿", "长城很长的", "天安门广场"]

        result = rerank(query, documents)

        assert len(result) == 3
        assert result[0]["text"] == "故宫是皇家宫殿"
        assert result[0]["score"] > result[1]["score"]

        reset_reranker()


class TestEmbeddingsMock:
    """测试 Embedding 模块（使用 mock）."""

    def test_embed_query_mock(self, monkeypatch):
        """测试查询向量化（mock 模型）."""
        import numpy as np
        from src.services.rag.embeddings import embed_query, reset_embedder

        # Mock SentenceTransformer
        class MockSentenceTransformer:
            def encode(self, texts, **kwargs):
                if isinstance(texts, str):
                    # 单个文本返回 1D 数组
                    return np.random.rand(384)
                # 批量文本返回 2D 数组
                return np.random.rand(len(texts), 384)

            def eval(self):
                pass

        monkeypatch.setattr(
            "src.services.rag.embeddings._embedder",
            MockSentenceTransformer(),
        )

        result = embed_query("测试查询")
        assert isinstance(result, list)
        assert len(result) == 384

        reset_embedder()

    def test_embed_documents_mock(self, monkeypatch):
        """测试批量文档向量化（mock 模型）."""
        import numpy as np
        from src.services.rag.embeddings import embed_documents, reset_embedder

        class MockSentenceTransformer:
            def encode(self, texts, **kwargs):
                return np.random.rand(len(texts), 384)

            def eval(self):
                pass

        monkeypatch.setattr(
            "src.services.rag.embeddings._embedder",
            MockSentenceTransformer(),
        )

        texts = ["文档1", "文档2", "文档3"]
        result = embed_documents(texts)
        assert isinstance(result, list)
        assert len(result) == 3
        assert len(result[0]) == 384

        reset_embedder()


class TestChromaClientMock:
    """测试 ChromaDB 客户端（使用 mock）."""

    def test_get_chroma_client_mock(self, monkeypatch):
        """测试获取 ChromaDB 客户端（mock）."""
        import chromadb
        from unittest.mock import MagicMock

        # Mock HttpClient
        mock_client = MagicMock()
        mock_client.get_version.return_value = "0.4.0"

        monkeypatch.setattr(
            "chromadb.HttpClient",
            lambda *args, **kwargs: mock_client,
        )

        from src.services.rag.chroma_client import get_chroma_client, reset_chroma_client
        reset_chroma_client()  # 重置单例

        client = get_chroma_client()
        assert client is not None

        reset_chroma_client()


class TestKnowledgeServiceSearch:
    """测试 KnowledgeService.search_spots（集成测试）."""

    @pytest.mark.asyncio
    async def test_search_spots_mock(self, monkeypatch):
        """测试搜索景点（mock 数据库）."""
        from src.services.knowledge_service import KnowledgeService
        from unittest.mock import AsyncMock, MagicMock

        # Mock 数据库会话
        mock_db = AsyncMock()

        # Mock 查询结果
        mock_spots = [
            MagicMock(
                id=1,
                name="故宫",
                city="北京",
                category="景点",
                description="皇家宫殿",
                rating=4.8,
                tags=["历史", "文化"],
            ),
            MagicMock(
                id=2,
                name="长城",
                city="北京",
                category="景点",
                description="世界奇迹",
                rating=4.9,
                tags=["自然", "奇观"],
            ),
        ]

        # 设置 mock 返回值
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = mock_spots
        mock_db.execute.return_value = mock_result

        # Mock RAG 模块
        monkeypatch.setattr(
            "src.services.knowledge_service.check_chroma_health",
            AsyncMock(return_value=False),  # ChromaDB 不可用
        )
        monkeypatch.setattr(
            "src.services.knowledge_service.rewrite_query",
            lambda q, c=None: f"{c} {q}" if c else q,
        )
        monkeypatch.setattr(
            "src.services.knowledge_service.extract_keywords",
            lambda q: ["故宫", "长城"],
        )
        monkeypatch.setattr(
            "src.services.knowledge_service.rrf_merge",
            lambda paths, **kwargs: [
                {"id": "1", "name": "故宫", "_rrf_score": 0.03},
                {"id": "2", "name": "长城", "_rrf_score": 0.02},
            ],
        )
        monkeypatch.setattr(
            "src.services.knowledge_service.rerank",
            lambda q, docs, **kwargs: [
                {"text": "故宫 皇家宫殿", "score": 0.9},
                {"text": "长城 世界奇迹", "score": 0.8},
            ],
        )

        # 执行搜索
        results = await KnowledgeService.search_spots(
            db=mock_db,
            query="北京景点",
            city="北京",
            limit=5,
        )

        assert isinstance(results, list)
        assert len(results) <= 5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
