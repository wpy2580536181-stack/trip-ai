"""Knowledge service (business logic)"""

import logging
import asyncio
from typing import Optional, List, Dict, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import selectinload

from src.models.spot import Spot
from src.schemas.knowledge import SpotCreate, SpotUpdate, SpotResponse
from src.exceptions import NotFoundException

logger = structlog.get_logger(__name__)

# RAG 检索相关导入
from src.services.rag import (
    get_spots_collection,
    check_chroma_health,
    rewrite_query,
    extract_keywords,
    rrf_merge,
    rerank,
)


def build_embedding_document(spot_data: dict) -> str:
    """Build embedding document from spot data
    
    Concatenate multiple fields to improve retrieval quality.
    City name and spot name are placed at the beginning (most important for embedding).
    """
    tags = " ".join(spot_data.get("tags", [])) if isinstance(spot_data.get("tags"), list) else ""
    return f"{spot_data.get('city', '')} {spot_data.get('name', '')} {spot_data.get('description', '')} {tags} {spot_data.get('category', '')}"


class KnowledgeService:
    """Knowledge service (business logic)"""
    
    @staticmethod
    async def get_spots(
        db: AsyncSession, 
        city: Optional[str] = None, 
        category: Optional[str] = None,
        page: int = 1, 
        page_size: int = 20
    ) -> tuple:
        """获取景点列表（分页，可按 city/category 筛选）
        
        Args:
            db: Database session
            city: Filter by city (optional)
            category: Filter by category (optional)
            page: Page number (1-based)
            page_size: Page size
            
        Returns:
            tuple: (spots, total)
        """
        # 1. Build query
        query = select(Spot)
        if city:
            query = query.where(Spot.city == city)
        if category:
            query = query.where(Spot.category == category)
        query = query.order_by(Spot.id.desc())
        
        # 2. Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)
        
        # 3. Get paginated results
        offset = (page - 1) * page_size
        result = await db.execute(
            query.offset(offset).limit(page_size)
        )
        spots = result.scalars().all()
        
        return spots, total
    
    @staticmethod
    async def get_spot(
        db: AsyncSession, 
        spot_id: int
    ) -> Spot:
        """获取单个景点详情
        
        Args:
            db: Database session
            spot_id: Spot ID
            
        Returns:
            Spot: Spot object
            
        Raises:
            NotFoundException: if spot not found
        """
        result = await db.execute(
            select(Spot).where(Spot.id == spot_id)
        )
        spot = result.scalar_one_or_none()
        
        if not spot:
            raise NotFoundException("景点")
        
        return spot
    
    @staticmethod
    async def create_spot(
        db: AsyncSession, 
        data: SpotCreate
    ) -> Spot:
        """创建景点（admin）
        
        Args:
            db: Database session
            data: Spot creation data
            
        Returns:
            Spot: Created spot
        """
        import uuid
        
        # 1. Generate vector_id
        vector_id = str(uuid.uuid4())
        
        # 2. Create spot
        spot = Spot(
            name=data.name,
            city=data.city,
            category=data.category,
            description=data.description,
            tags=data.tags,
            avg_cost=data.avg_cost,
            duration=data.duration,
            open_time=data.open_time,
            rating=data.rating,
            vector_id=vector_id
        )
        
        db.add(spot)
        await db.commit()
        await db.refresh(spot)
        
        # 3. Sync to ChromaDB (non-blocking)
        try:
            from src.services.rag.chroma_client import get_spots_collection
            from src.services.rag.embeddings import embed_query_async

            logger.info("同步景点到 ChromaDB", spot_id=spot.id, name=spot.name)

            collection = await get_spots_collection()
            doc_text = build_embedding_document({
                "city": spot.city,
                "name": spot.name,
                "description": spot.description,
                "tags": spot.tags,
                "category": spot.category
            })
            embedding = await embed_query_async(doc_text)

            await collection.add(
                ids=[vector_id],
                embeddings=[embedding],
                documents=[doc_text],
                metadatas=[{
                    "city": spot.city,
                    "name": spot.name,
                    "category": spot.category,
                    "tags": spot.tags,
                    "rating": spot.rating or 0,
                }]
            )
        except Exception as e:
            logger.warning("Chroma sync failed (MySQL data saved)", error=str(e))

        return spot
    
    @staticmethod
    async def update_spot(
        db: AsyncSession, 
        spot_id: int, 
        data: SpotUpdate
    ) -> Spot:
        """更新景点（admin）
        
        Args:
            db: Database session
            spot_id: Spot ID
            data: Spot update data
            
        Returns:
            Spot: Updated spot
            
        Raises:
            NotFoundException: if spot not found
        """
        # 1. Find spot
        result = await db.execute(
            select(Spot).where(Spot.id == spot_id)
        )
        spot = result.scalar_one_or_none()
        
        if not spot:
            raise NotFoundException("景点")
        
        # 2. Update fields
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(spot, field):
                setattr(spot, field, value)
        
        await db.commit()
        await db.refresh(spot)
        
        # 3. Sync to ChromaDB (non-blocking)
        if spot.vector_id:
            try:
                from src.services.rag.chroma_client import get_spots_collection
                from src.services.rag.embeddings import embed_query_async

                logger.info("更新 ChromaDB 向量", spot_id=spot.id, name=spot.name)

                collection = await get_spots_collection()

                # Delete old vector
                await collection.delete(ids=[spot.vector_id])

                # Add new vector
                doc_text = build_embedding_document({
                    "city": spot.city,
                    "name": spot.name,
                    "description": spot.description,
                    "tags": spot.tags,
                    "category": spot.category
                })
                embedding = await embed_query_async(doc_text)

                await collection.add(
                    ids=[spot.vector_id],
                    embeddings=[embedding],
                    documents=[doc_text],
                    metadatas=[{
                        "city": spot.city,
                        "name": spot.name,
                        "category": spot.category,
                        "tags": spot.tags,
                        "rating": spot.rating or 0,
                    }]
                )
            except Exception as e:
                logger.warning("Chroma sync failed (MySQL data updated)", error=str(e))

        return spot
    
    @staticmethod
    async def delete_spot(
        db: AsyncSession, 
        spot_id: int
    ) -> bool:
        """删除景点（admin）
        
        Args:
            db: Database session
            spot_id: Spot ID
            
        Returns:
            bool: True if successful
            
        Raises:
            NotFoundException: if spot not found
        """
        # 1. Find spot
        result = await db.execute(
            select(Spot).where(Spot.id == spot_id)
        )
        spot = result.scalar_one_or_none()
        
        if not spot:
            raise NotFoundException("景点")
        
        # 2. Delete from ChromaDB (non-blocking)
        if spot.vector_id:
            try:
                from src.services.rag.chroma_client import get_spots_collection

                logger.info("从 ChromaDB 删除向量", spot_id=spot.id, vector_id=spot.vector_id)

                collection = await get_spots_collection()
                await collection.delete(ids=[spot.vector_id])
            except Exception as e:
                logger.warning("Chroma delete failed (MySQL data will be deleted)", error=str(e))

        # 3. Delete from MySQL
        await db.delete(spot)
        await db.commit()

        return True

    @staticmethod
    async def search_spots(
        db: AsyncSession,
        query: str,
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """RAG 三路并行召回检索景点.

        实现三路并行召回：
        - 路径 1: ChromaDB 向量检索
        - 路径 2: MySQL FULLTEXT 搜索
        - 路径 3: 评分排序（作为基础召回）

        使用 RRF 融合三路结果，然后使用 Cross-Encoder 重排 top-N 结果。

        Args:
            db: 数据库会话.
            query: 用户查询文本.
            city: 目标城市（可选）.
            category: 景点类型（可选）.
            limit: 返回结果数量（默认 5）.
            user_id: 用户 ID（可选，用于个性化）.

        Returns:
            List[Dict[str, Any]]: 检索到的景点列表，按相关性排序。

        Example:
            >>> results = await search_spots(db, "北京故宫", city="北京", limit=5)
            >>> len(results)
            5
        """
        # 1. 本地查询改写
        rewritten_query = rewrite_query(query, city)
        keywords = extract_keywords(query)
        logger.info(
            "RAG 检索开始",
            query=query,
            rewritten_query=rewritten_query,
            city=city,
            limit=limit,
        )

        # 2. 检查 ChromaDB 可用性
        chroma_available = await check_chroma_health()

        # 3. 三路并行召回
        tasks = []

        # 路径 1: ChromaDB 向量检索
        if chroma_available:
            task1 = asyncio.create_task(
                KnowledgeService._chroma_search(rewritten_query, city, category, limit * 2)
            )
            tasks.append(("chroma", task1))
        else:
            logger.warning("ChromaDB 不可用，跳过向量检索")

        # 路径 2: MySQL FULLTEXT 搜索
        task2 = asyncio.create_task(
            KnowledgeService._mysql_fulltext_search(db, keywords, city, category, limit * 2)
        )
        tasks.append(("mysql_fulltext", task2))

        # 路径 3: MySQL 评分排序（基础召回）
        task3 = asyncio.create_task(
            KnowledgeService._mysql_rating_search(db, city, category, limit * 2)
        )
        tasks.append(("mysql_rating", task3))

        # 等待所有任务完成（收集异常，不中断）
        results = {}
        for name, task in tasks:
            try:
                result = await task
                results[name] = result
                logger.debug(f"召回路径 {name} 完成", count=len(result))
            except Exception as e:
                logger.error(f"召回路径 {name} 失败", error=str(e))
                results[name] = []

        path1 = results.get("chroma", [])
        path2 = results.get("mysql_fulltext", [])
        path3 = results.get("mysql_rating", [])

        # 4. RRF 融合
        fused = rrf_merge([path1, path2, path3], id_key="id")
        logger.info("RRF 融合完成", fused_count=len(fused))

        if not fused:
            logger.warning("RRF 融合后无结果")
            return []

        # 5. Cross-Encoder 重排 top-N
        rerank_candidates = fused[:20]  # 取前 20 个进行重排

        # 优化：如果第一名分数远高于其他，跳过重排
        skip_rerank = (
            len(rerank_candidates) > 0
            and rerank_candidates[0].get("_rrf_score", 0) > 0.04
        )

        if len(rerank_candidates) > 1 and not skip_rerank:
            try:
                # 准备重排文档
                rerank_docs = [
                    KnowledgeService._build_spot_document(c) for c in rerank_candidates
                ]

                # 执行重排
                reranked = rerank(rewritten_query, rerank_docs, top_k=min(limit, len(rerank_candidates)))

                # 按重排结果重新映射
                reranked_map = {r["text"]: i for i, r in enumerate(reranked)}
                reranked_items = sorted(
                    rerank_candidates,
                    key=lambda x: reranked_map.get(
                        KnowledgeService._build_spot_document(x), 999
                    ),
                )[:limit]

                logger.info("重排完成", reranked_count=len(reranked_items))
                return reranked_items
            except Exception as e:
                logger.error("重排失败，降级到 RRF 排序", error=str(e))
                # 降级：使用 RRF 排序结果

        # 6. 返回最终结果
        final_items = fused[:limit]
        logger.info("RAG 检索完成", final_count=len(final_items))
        return final_items

    @staticmethod
    async def _chroma_search(
        query: str,
        city: Optional[str] = None,
        category: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """ChromaDB 向量检索.

        Args:
            query: 查询文本.
            city: 城市过滤.
            category: 类型过滤.
            n_results: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: 检索结果列表.
        """
        try:
            from src.services.rag.embeddings import embed_query_async
            from src.services.rag.chroma_client import get_spots_collection

            # 异步生成查询向量
            query_embedding = await embed_query_async(query)

            # 构造过滤条件
            where_filter = {}
            if city:
                where_filter["city"] = city
            if category:
                where_filter["category"] = category

            # 获取集合
            collection = await get_spots_collection()

            # 在线程池中执行向量检索（ChromaDB Python 客户端是同步的）
            def _do_query():
                return collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where=where_filter if where_filter else None,
                    include=["metadatas", "documents", "distances"],
                )

            results = await asyncio.to_thread(_do_query)

            # 解析结果
            spots = []
            if results and results.get("ids"):
                # 收集所有 ChromaDB IDs（vector_id）
                chroma_ids = results["ids"][0]

                # 批量查询 MySQL 获取真实的 spot id
                from sqlalchemy.orm import selectinload
                from src.models.spot import Spot

                result = await db.execute(
                    select(Spot.id, Spot.vector_id).where(
                        Spot.vector_id.in_(chroma_ids)
                    )
                )
                vector_id_map = {row[1]: str(row[0]) for row in result}

                for i, chroma_id in enumerate(chroma_ids):
                    metadata = results["metadatas"][0][i] if results.get("metadatas") else {}
                    document = results["documents"][0][i] if results.get("documents") else ""
                    distance = results["distances"][0][i] if results.get("distances") else 0.0

                    # 使用 MySQL 的真实 id（通过 vector_id 映射）
                    real_id = vector_id_map.get(chroma_id, chroma_id)

                    spots.append({
                        "id": real_id,
                        "name": metadata.get("name", ""),
                        "city": metadata.get("city", ""),
                        "category": metadata.get("category", ""),
                        "rating": metadata.get("rating", 0),
                        "score": 1.0 - distance,  # 转换距离为相似度
                        "_source": "chroma",
                    })

            logger.debug("ChromaDB 检索完成", count=len(spots))
            return spots
        except Exception as e:
            logger.error("ChromaDB 检索失败", error=str(e))
            return []

    @staticmethod
    async def _mysql_fulltext_search(
        db: AsyncSession,
        keywords: List[str],
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """MySQL FULLTEXT 搜索.

        使用 MySQL 的全文索引进行关键词检索。

        Args:
            db: 数据库会话.
            keywords: 关键词列表.
            city: 城市过滤.
            category: 类型过滤.
            limit: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: 检索结果列表.
        """
        try:
            if not keywords:
                return []

            # 构造 MATCH...AGAINST 查询
            search_text = " ".join(keywords)

            query = select(Spot).where(
                func.match(Spot.name, Spot.description).against(search_text)
            )

            if city:
                query = query.where(Spot.city == city)
            if category:
                query = query.where(Spot.category == category)

            query = query.order_by(Spot.rating.desc()).limit(limit)

            result = await db.execute(query)
            spots = result.scalars().all()

            # 转换为字典格式
            spot_dicts = []
            for spot in spots:
                spot_dicts.append({
                    "id": str(spot.id),
                    "name": spot.name,
                    "city": spot.city,
                    "category": spot.category,
                    "description": spot.description,
                    "rating": spot.rating or 0,
                    "tags": spot.tags,
                    "_source": "mysql_fulltext",
                })

            logger.debug("MySQL FULLTEXT 检索完成", count=len(spot_dicts))
            return spot_dicts
        except Exception as e:
            logger.error("MySQL FULLTEXT 检索失败", error=str(e))
            # 降级：使用 LIKE 模糊匹配
            return await KnowledgeService._mysql_like_search(db, keywords, city, category, limit)

    @staticmethod
    async def _mysql_like_search(
        db: AsyncSession,
        keywords: List[str],
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """MySQL LIKE 模糊匹配（FULLTEXT 失败时的降级方案）.

        Args:
            db: 数据库会话.
            keywords: 关键词列表.
            city: 城市过滤.
            category: 类型过滤.
            limit: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: 检索结果列表.
        """
        try:
            query = select(Spot)

            # 构造 LIKE 条件
            like_conditions = []
            for keyword in keywords[:3]:  # 限制关键词数量
                like_conditions.append(Spot.name.like(f"%{keyword}%"))
                like_conditions.append(Spot.description.like(f"%{keyword}%"))

            if like_conditions:
                query = query.where(func.or_(*like_conditions))

            if city:
                query = query.where(Spot.city == city)
            if category:
                query = query.where(Spot.category == category)

            query = query.order_by(Spot.rating.desc()).limit(limit)

            result = await db.execute(query)
            spots = result.scalars().all()

            spot_dicts = []
            for spot in spots:
                spot_dicts.append({
                    "id": str(spot.id),
                    "name": spot.name,
                    "city": spot.city,
                    "category": spot.category,
                    "description": spot.description,
                    "rating": spot.rating or 0,
                    "tags": spot.tags,
                    "_source": "mysql_like",
                })

            logger.debug("MySQL LIKE 检索完成", count=len(spot_dicts))
            return spot_dicts
        except Exception as e:
            logger.error("MySQL LIKE 检索失败", error=str(e))
            return []

    @staticmethod
    async def _mysql_rating_search(
        db: AsyncSession,
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """MySQL 评分排序检索（基础召回）.

        按评分排序返回热门景点，作为基础召回路径。

        Args:
            db: 数据库会话.
            city: 城市过滤.
            category: 类型过滤.
            limit: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: 检索结果列表.
        """
        try:
            query = select(Spot)

            if city:
                query = query.where(Spot.city == city)
            if category:
                query = query.where(Spot.category == category)

            query = query.order_by(Spot.rating.desc()).limit(limit)

            result = await db.execute(query)
            spots = result.scalars().all()

            spot_dicts = []
            for spot in spots:
                spot_dicts.append({
                    "id": str(spot.id),
                    "name": spot.name,
                    "city": spot.city,
                    "category": spot.category,
                    "description": spot.description,
                    "rating": spot.rating or 0,
                    "tags": spot.tags,
                    "_source": "mysql_rating",
                })

            logger.debug("MySQL 评分检索完成", count=len(spot_dicts))
            return spot_dicts
        except Exception as e:
            logger.error("MySQL 评分检索失败", error=str(e))
            return []

    @staticmethod
    def _build_spot_document(spot: Dict[str, Any]) -> str:
        """构建用于重排序的文档文本.

        Args:
            spot: 景点字典.

        Returns:
            str: 文档文本.
        """
        tags = " ".join(spot.get("tags", [])) if isinstance(spot.get("tags"), list) else ""
        return f"{spot.get('city', '')} {spot.get('name', '')} {spot.get('description', '')} {tags} {spot.get('category', '')}"

    @staticmethod
    async def format_search_results(
        spots: List[Dict[str, Any]],
        include_details: bool = True,
    ) -> str:
        """格式化检索结果为文本（用于 LLM 上下文）.

        Args:
            spots: 景点列表.
            include_details: 是否包含详细信息.

        Returns:
            str: 格式化的文本.
        """
        if not spots:
            return "未找到相关景点信息。"

        lines = [f"找到 {len(spots)} 个相关景点：\n"]

        for i, spot in enumerate(spots, 1):
            lines.append(f"{i}. {spot.get('name', '未知景点')}（{spot.get('city', '未知城市')}）")
            if include_details:
                if spot.get("rating"):
                    lines.append(f"   - 评分：{spot['rating']} 分")
                if spot.get("description"):
                    desc = spot["description"][:100] + "..." if len(spot["description"]) > 100 else spot["description"]
                    lines.append(f"   - 介绍：{desc}")
                if spot.get("tags"):
                    tags = spot["tags"] if isinstance(spot["tags"], list) else []
                    lines.append(f"   - 标签：{', '.join(tags)}")

        return "\n".join(lines)
