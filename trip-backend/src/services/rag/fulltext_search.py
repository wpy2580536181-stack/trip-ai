"""PostgreSQL 全文检索模块（zhparser 中文分词）.

替代原 MySQL FULLTEXT + MATCH...AGAINST 查询，
使用 PostgreSQL tsvector + zhparser 实现中文全文检索。
"""

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def fulltext_search_spots(
    db: AsyncSession,
    keywords: List[str],
    city: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """PostgreSQL 全文检索 spots 表.

    使用 zhparser 中文分词配置，通过 websearch_to_tsquery 构造查询。

    Args:
        db: 数据库会话.
        keywords: 关键词列表.
        city: 城市过滤.
        category: 类型过滤.
        limit: 返回结果数量.

    Returns:
        景点字典列表。
    """
    try:
        if not keywords:
            return []

        search_text = " ".join(keywords)

        sql = """
            SELECT id, name, city, category, description, rating, tags,
                   ts_rank(
                       to_tsvector('chinese', coalesce(name, '') || ' ' || coalesce(description, '')),
                       websearch_to_tsquery('chinese', :q)
                   ) AS rank
            FROM spots
            WHERE to_tsvector('chinese', coalesce(name, '') || ' ' || coalesce(description, ''))
                  @@ websearch_to_tsquery('chinese', :q)
        """
        params: Dict[str, Any] = {"q": search_text, "limit": limit}

        if city:
            sql += " AND city = :city"
            params["city"] = city
        if category:
            sql += " AND category = :category"
            params["category"] = category

        sql += " ORDER BY rating DESC NULLS LAST LIMIT :limit"

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
                "_source": "pg_fulltext",
            })

        logger.debug("PG 全文检索 spots 完成", count=len(spots))
        return spots
    except Exception as e:
        logger.error("PG 全文检索 spots 失败", error=str(e))
        # 降级：LIKE 模糊匹配
        return await _like_search_spots(db, keywords, city, category, limit)


async def fulltext_search_spot_docs(
    db: AsyncSession,
    keywords: List[str],
    city: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """PostgreSQL 全文检索 spot_docs 表.

    Args:
        db: 数据库会话.
        keywords: 关键词列表.
        city: 城市过滤（JOIN spots）.
        limit: 返回结果数量.

    Returns:
        文档块字典列表。
    """
    try:
        if not keywords:
            return []

        search_text = " ".join(keywords)

        sql = """
            SELECT sd.id, sd.spot_id, sd.source_type, sd.source_name,
                   sd.source_url, sd.content, sd.credibility_score
            FROM spot_docs sd
        """
        params: Dict[str, Any] = {"q": search_text, "limit": limit}

        if city:
            sql += " JOIN spots s ON sd.spot_id = s.id"
            sql += """ WHERE to_tsvector('chinese', coalesce(sd.content, ''))
                       @@ websearch_to_tsquery('chinese', :q)
                       AND s.city = :city"""
            params["city"] = city
        else:
            sql += """ WHERE to_tsvector('chinese', coalesce(sd.content, ''))
                       @@ websearch_to_tsquery('chinese', :q)"""

        sql += " ORDER BY sd.credibility_score DESC LIMIT :limit"

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
                "score": float(row.credibility_score or 0.5),
            })

        logger.debug("PG 全文检索 spot_docs 完成", count=len(hits))
        return hits
    except Exception as e:
        logger.error("PG 全文检索 spot_docs 失败", error=str(e))
        return []


async def _like_search_spots(
    db: AsyncSession,
    keywords: List[str],
    city: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """LIKE 模糊匹配（全文检索失败时的降级方案）."""
    try:
        from sqlalchemy import select, or_
        from src.models.spot import Spot

        like_conds = [Spot.name.like(f"%{kw}%") | Spot.description.like(f"%{kw}%") for kw in keywords]
        query = select(Spot).where(or_(*like_conds))

        if city:
            query = query.where(Spot.city == city)
        if category:
            query = query.where(Spot.category == category)

        query = query.order_by(Spot.rating.desc().nullslast()).limit(limit)
        result = await db.execute(query)
        spots_rows = result.scalars().all()

        return [
            {
                "id": str(s.id),
                "name": s.name,
                "city": s.city,
                "category": s.category,
                "description": s.description,
                "rating": s.rating or 0,
                "tags": s.tags,
                "_source": "pg_like",
            }
            for s in spots_rows
        ]
    except Exception as e:
        logger.error("LIKE 降级检索失败", error=str(e))
        return []
