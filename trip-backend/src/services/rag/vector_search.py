"""pgvector 向量检索模块.

替代原 ChromaDB 向量检索，直接在 PostgreSQL 内通过 pgvector 扩展
执行 HNSW 余弦相似度检索。
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.spot import Spot
from src.models.spot_doc import SpotDoc

logger = logging.getLogger(__name__)


async def vector_search_spots(
    db: AsyncSession,
    query_embedding: List[float],
    city: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """pgvector 余弦相似度检索 spots 表.

    使用 HNSW 索引加速，返回按相似度降序排列的结果。

    Args:
        db: 数据库会话.
        query_embedding: 查询向量（512 维）.
        city: 城市过滤.
        category: 类型过滤.
        limit: 返回结果数量.

    Returns:
        景点字典列表，含 score 字段（余弦相似度 0~1）。
    """
    try:
        # 使用原生 SQL 以利用 pgvector 操作符 <=>（余弦距离）
        # score = 1 - cosine_distance
        # 注意：不能用 :vec::vector（与 SQLAlchemy 绑定参数冲突），需用 CAST
        sql = """
            SELECT id, name, city, category, description, rating, tags,
                   1 - (embedding <=> CAST(:vec AS vector)) AS score
            FROM spots
            WHERE embedding IS NOT NULL
        """
        params: Dict[str, Any] = {"vec": str(query_embedding), "limit": limit}

        if city:
            sql += " AND city = :city"
            params["city"] = city
        if category:
            sql += " AND category = :category"
            params["category"] = category

        sql += " ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :limit"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        spots = []
        for row in rows:
            spots.append({
                "id": str(row.id),
                "name": row.name,
                "city": row.city,
                "category": row.category,
                "description": row.description,
                "rating": row.rating or 0,
                "tags": row.tags,
                "score": float(row.score),
                "_source": "pgvector",
            })

        logger.debug("pgvector spots 检索完成", count=len(spots))
        return spots
    except Exception as e:
        logger.error("pgvector spots 检索失败", error=str(e))
        return []


async def vector_search_spot_docs(
    db: AsyncSession,
    query_embedding: List[float],
    city: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """pgvector 检索 spot_docs 表（文本层向量召回）.

    返回文档块级结果，含可信度与来源信息，供后续聚合到 spot 级。

    Args:
        db: 数据库会话.
        query_embedding: 查询向量（512 维）.
        city: 城市过滤（通过 JOIN spots 表）.
        limit: 返回结果数量.

    Returns:
        文档块字典列表，含 score / credibility_score / evidence 等字段。
    """
    try:
        sql = """
            SELECT sd.id, sd.spot_id, sd.source_type, sd.source_name,
                   sd.source_url, sd.content, sd.credibility_score,
                   1 - (sd.embedding <=> CAST(:vec AS vector)) AS score
            FROM spot_docs sd
        """
        params: Dict[str, Any] = {"vec": str(query_embedding), "limit": limit}

        if city:
            sql += " JOIN spots s ON sd.spot_id = s.id"
            sql += " WHERE sd.embedding IS NOT NULL AND s.city = :city"
            params["city"] = city
        else:
            sql += " WHERE sd.embedding IS NOT NULL"

        sql += " ORDER BY sd.embedding <=> CAST(:vec AS vector) LIMIT :limit"

        result = await db.execute(text(sql), params)
        rows = result.fetchall()

        hits = []
        for row in rows:
            hits.append({
                "spot_id": str(row.spot_id),
                "source_type": row.source_type,
                "source_name": row.source_name,
                "source_url": row.source_url,
                "content": row.content,
                "credibility_score": float(row.credibility_score or 0.5),
                "score": float(row.score),
            })

        logger.debug("pgvector spot_docs 检索完成", count=len(hits))
        return hits
    except Exception as e:
        logger.error("pgvector spot_docs 检索失败", error=str(e))
        return []
