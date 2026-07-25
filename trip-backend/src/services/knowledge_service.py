"""Knowledge service (business logic)"""

import json
import logging
import asyncio
from typing import Optional, List, Dict, Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, or_
from sqlalchemy.orm import selectinload

from src.models.spot import Spot
from src.models.spot_doc import SpotDoc
from src.schemas.knowledge import SpotCreate, SpotUpdate, SpotResponse
from src.exceptions import NotFoundException

logger = structlog.get_logger(__name__)

# RAG 检索相关导入
from src.services.rag import (
    get_spots_collection,
    get_spot_docs_collection,
    check_chroma_health,
    rewrite_query,
    extract_keywords,
    rrf_merge,
    rrf_merge_with_weights,
    rerank,
    rerank_with_credibility,
)
from src.services.rag.credibility import weight_by_credibility


def build_embedding_document(spot_data: dict) -> str:
    """Build embedding document from spot data
    
    Concatenate multiple fields to improve retrieval quality.
    City name and spot name are placed at the beginning (most important for embedding).
    """
    tags = " ".join(spot_data.get("tags", [])) if isinstance(spot_data.get("tags"), list) else ""
    return f"{spot_data.get('city', '')} {spot_data.get('name', '')} {spot_data.get('description', '')} {tags} {spot_data.get('category', '')}"


def _aggregate_spot_docs(hits: List[Dict[str, Any]], max_chunks: int = 3) -> List[Dict[str, Any]]:
    """把 chunk 级命中聚合为 spot 级结果，保留每个 spot 命中的 top-k 块作证据。

    旧逻辑只保留「可信度最高」的 1 块，但同 spot 各块 credibility 相同 → 实际任取 1 块，
    长文其余切片仅贡献召回、不进证据。这里改为按分数降序取前 max_chunks 块，全部拼进
    evidence（content 为拼接串，chunks 为结构化多块），让检索/重排/LLM 看到完整切片。
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for h in hits:
        sid = h.get("spot_id")
        if not sid:
            continue
        groups.setdefault(sid, []).append(h)

    out: List[Dict[str, Any]] = []
    for sid, chunk_hits in groups.items():
        # 按分数降序（Chroma 取相似度最高；MySQL 兜底各块同分则稳定保序）
        chunk_hits.sort(key=lambda x: x.get("score", 0.0), reverse=True)
        top = chunk_hits[:max_chunks]
        best = top[0]
        ev_chunks = [
            {"content": c["content"], "credibility_score": c["credibility_score"]}
            for c in top
        ]
        out.append({
            "id": sid,
            "name": "",
            "city": "",
            "category": "",
            "rating": 0,
            "score": best.get("score", 0.5),
            "_source": "spot_docs",
            "source_type": best["source_type"],
            "source_name": best["source_name"],
            "source_url": best["source_url"],
            "credibility_score": best["credibility_score"],
            "evidence": {
                "source_type": best["source_type"],
                "source_name": best["source_name"],
                "source_url": best["source_url"],
                "content": "\n".join(c["content"] for c in top),
                "chunks": ev_chunks,
                "credibility_score": best["credibility_score"],
            },
        })
    return out


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
    async def list_spot_docs(
        db: AsyncSession,
        city: Optional[str] = None,
        source_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple:
        """获取文本层文档块列表（分页，可按 city/source_type 筛选，关联景点名/城市）.

        Args:
            db: Database session
            city: Filter by spot city (optional)
            source_type: Filter by source type (optional, e.g. wiki/wikidata)
            page: Page number (1-based)
            page_size: Page size

        Returns:
            tuple: (rows, total)，rows 为 [(SpotDoc, spot_name, spot_city), ...]
        """
        query = (
            select(SpotDoc, Spot.name, Spot.city)
            .join(Spot, Spot.id == SpotDoc.spot_id, isouter=True)
        )
        if city:
            query = query.where(Spot.city == city)
        if source_type:
            query = query.where(SpotDoc.source_type == source_type)
        query = query.order_by(SpotDoc.id.desc())

        count_query = select(func.count()).select_from(query.subquery())
        total = await db.scalar(count_query)

        offset = (page - 1) * page_size
        result = await db.execute(query.offset(offset).limit(page_size))
        rows = result.all()

        return rows, total
    
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
        
        # 3. 异步同步到 ChromaDB（入队；worker 异步消费，API 立即返回）
        # 改造（决策文档 §3.1 / M1）：原同步块耗时 1-3s 拖慢 API P95 至 800ms+；
        # 改为入队让 worker 异步处理。失败抛错也不影响 API 返回（MySQL 已落库）。
        # 脏数据修复：scripts/chroma_reindex.py --force 全量重建。
        try:
            from src.services.tasks.chroma_sync import enqueue_spot_chroma_sync

            await enqueue_spot_chroma_sync(
                spot_id=spot.id,
                vector_id=vector_id,
                city=spot.city,
                name=spot.name,
                description=spot.description,
                tags=spot.tags,
                category=spot.category,
                rating=spot.rating,
                job_kind="create",
            )
            logger.info("Chroma sync enqueued", spot_id=spot.id, name=spot.name)
        except Exception as e:
            logger.warning("Chroma sync enqueue failed (MySQL data saved)", error=str(e))

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
        
        # 3. 异步同步到 ChromaDB（入队；worker 用 upsert 替代"先 delete 再 add"）
        # 改造（M1）：原同步块"先 delete 再 add"有中间态——如果 delete 成功但 add 失败
        # 会留下"spot 在 MySQL 但 Chroma 找不到"窗口；改用 upsert 一个原子操作搞定。
        if spot.vector_id:
            try:
                from src.services.tasks.chroma_sync import enqueue_spot_chroma_sync

                await enqueue_spot_chroma_sync(
                    spot_id=spot.id,
                    vector_id=spot.vector_id,
                    city=spot.city,
                    name=spot.name,
                    description=spot.description,
                    tags=spot.tags,
                    category=spot.category,
                    rating=spot.rating,
                    job_kind="update",
                )
                logger.info("Chroma sync (update) enqueued", spot_id=spot.id, name=spot.name)
            except Exception as e:
                logger.warning("Chroma sync enqueue failed (MySQL data updated)", error=str(e))

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
                from src.services.rag.chroma_client import get_spots_collection, run_sync

                logger.info("从 ChromaDB 删除向量", spot_id=spot.id, vector_id=spot.vector_id)

                collection = await get_spots_collection()
                await run_sync(collection.delete, ids=[spot.vector_id])
            except Exception as e:
                logger.warning("Chroma delete failed (MySQL data will be deleted)", error=str(e))

        # 3. Delete from MySQL
        await db.delete(spot)
        await db.commit()

        return True

    @staticmethod
    async def search_spots(
        db: Optional[AsyncSession] = None,
        query: str = "",
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 5,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """RAG 多路并行召回检索景点（事实层 + 文本层）.

        四路并行召回：
        - 路径 1: ChromaDB spots 事实向量检索
        - 路径 2: ChromaDB spot_docs 文本向量召回（真实外部文本，带 MySQL FULLTEXT 兜底）
        - 路径 3: MySQL FULLTEXT(spots) 关键词
        - 路径 4: MySQL 评分排序（基础召回）

        用 rrf_merge_with_weights + 可信度调节器融合四路，再用 Cross-Encoder
        重排（叠加可信度特征），结果仍返回 Spot 级，但会附带来自文本层的
        真实证据片段（source_type / source_url / credibility_score），让 LLM
        拿到模型参数外的新信息。

        Args:
            db: 数据库会话（可选；省略时自动新建并关闭会话，便于 agent 工具/脚本调用）.
            query: 用户查询文本.
            city: 目标城市（可选）.
            category: 景点类型（可选）.
            limit: 返回结果数量（默认 5）.
            user_id: 用户 ID（可选，用于个性化）.

        Returns:
            List[Dict[str, Any]]: 检索到的景点列表，按相关性排序，可能含 evidence 字段。
        """
        # 0. 会话：允许不传 db（agent 工具/脚本场景自动建会话）
        own_session = False
        if db is None:
            from src.config.database import async_session

            db = async_session()
            own_session = True
        try:
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

            # 3. 四路并行召回
            tasks = []

            # 路径 1: ChromaDB spots 事实向量检索
            if chroma_available:
                task1 = asyncio.create_task(
                    KnowledgeService._chroma_search(rewritten_query, city, category, limit * 2)
                )
                tasks.append(("chroma", task1))
            else:
                logger.warning("ChromaDB 不可用，跳过事实向量检索")

            # 路径 2: spot_docs 文本层召回（真实外部文本）
            task_docs = asyncio.create_task(
                KnowledgeService._spot_docs_search(db, rewritten_query, keywords, city, category, limit * 2)
            )
            tasks.append(("spot_docs", task_docs))

            # 路径 3: MySQL FULLTEXT(spots) 搜索
            task2 = asyncio.create_task(
                KnowledgeService._mysql_fulltext_search(db, keywords, city, category, limit * 2)
            )
            tasks.append(("mysql_fulltext", task2))

            # 路径 4: MySQL 评分排序（基础召回）
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

            path_chroma = results.get("chroma", [])
            path_docs = results.get("spot_docs", [])
            path_mysql_ft = results.get("mysql_fulltext", [])
            path_mysql_rating = results.get("mysql_rating", [])

            # 4. 加权 RRF 融合（可信度调节权重）
            #    权重：事实向量 1.0 / 文本向量 0.9 / mysql全文 0.7 / 评分 0.5
            paths = [path_chroma, path_docs, path_mysql_ft, path_mysql_rating]
            weights = [1.0, 0.9, 0.7, 0.5]
            try:
                fused = rrf_merge_with_weights(
                    paths,
                    weights,
                    id_key="id",
                    score_adjuster=weight_by_credibility,
                )
            except Exception as e:
                logger.error("加权 RRF 失败，降级为普通 RRF", error=str(e))
                fused = rrf_merge([path_chroma, path_docs, path_mysql_ft, path_mysql_rating], id_key="id")
            logger.info("RRF 融合完成", fused_count=len(fused))

            # 4.5 把文本层证据/可信度显式挂回融合结果（不受 RRF 合并顺序覆盖影响）
            evidence_by_spot: Dict[str, Dict[str, Any]] = {}
            for d in path_docs:
                sid = str(d.get("id"))
                if d.get("evidence") and sid not in evidence_by_spot:
                    evidence_by_spot[sid] = d
            for item in fused:
                ev = evidence_by_spot.get(str(item.get("id")))
                if ev:
                    item["evidence"] = ev.get("evidence")
                    item["credibility_score"] = max(
                        float(item.get("credibility_score", 0.0) or 0.0),
                        float(ev.get("credibility_score", 0.0) or 0.0),
                    )
                    item["source_type"] = ev.get("source_type")
                    item["source_url"] = ev.get("source_url")
                    item["source_name"] = ev.get("source_name")

            if not fused:
                logger.warning("RRF 融合后无结果")
                return []

            # 5. Cross-Encoder 重排（叠加可信度特征）
            rerank_candidates = fused[:20]  # 取前 20 个进行重排

            # 优化：如果第一名分数远高于其他，跳过重排
            skip_rerank = (
                len(rerank_candidates) > 0
                and rerank_candidates[0].get("_rrf_score", 0) > 0.04
            )

            if len(rerank_candidates) > 1 and not skip_rerank:
                try:
                    # 准备重排文档（含文本层真实证据片段）
                    rerank_docs = [
                        KnowledgeService._build_spot_document(c) for c in rerank_candidates
                    ]
                    # 可信度特征：带 spot_docs 真实来源的候选用其显式 credibility_score；
                    # 无外部文本来源的景点取中下位 0.3，确保真实引用源（wiki/官方等）
                    # 在重排中不被"无来源"的高评分景点压制（避免证据被 top_k 截断丢弃）。
                    creds = []
                    for c in rerank_candidates:
                        cs = c.get("credibility_score")
                        if isinstance(cs, (int, float)):
                            creds.append(float(cs))
                        else:
                            creds.append(0.3)

                    # 执行重排（可信度后置微调）
                    reranked = rerank_with_credibility(
                        rewritten_query,
                        rerank_docs,
                        creds,
                        top_k=min(limit, len(rerank_candidates)),
                    )

                    # 按重排结果重新映射（使用 final_score）
                    reranked_map = {
                        r["text"]: r.get("final_score", r["score"]) for r in reranked
                    }
                    reranked_items = sorted(
                        rerank_candidates,
                        key=lambda x: reranked_map.get(
                            KnowledgeService._build_spot_document(x), -1.0
                        ),
                        reverse=True,
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

        finally:
            if own_session:
                await db.close()

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
            from src.services.rag.chroma_client import get_spots_collection, run_sync

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

            results = await run_sync(_do_query)

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
    def _chinese_like_terms(texts: List[str], max_terms: int = 8) -> List[str]:
        """为中文文本生成 LIKE 检索词：原词 + 2 字滑动窗口。

        中文无空格分词，extract_keywords 常返回未切分的整串（如 '北京故宫博物院'），
        直接 LIKE 整串难以命中。拆成 2 字窗口（故宫/博物/...）可稳定召回，
        用于 MySQL 兜底路径（Chroma 向量召回为主）。
        """
        terms: List[str] = []
        seen = set()
        for t in texts:
            pieces = [t] + [t[i:i + 2] for i in range(len(t) - 1)]
            for p in pieces:
                if len(p) >= 2 and p not in seen:
                    seen.add(p)
                    terms.append(p)
                if len(terms) >= max_terms:
                    return terms
        return terms

    @staticmethod
    async def _spot_docs_search(
        db: AsyncSession,
        query: str,
        keywords: List[str],
        city: Optional[str] = None,
        category: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """文本层 spot_docs 召回（真实外部文本）.

        优先 Chroma(spot_docs) 向量召回；Chroma 不可用时降级为
        MySQL FULLTEXT(spot_docs) 关键词召回。命中结果映射回 spot_id，
        返回 Spot 级结果并携带可信度与证据片段，供加权 RRF 融合与重排使用。

        Args:
            db: 数据库会话.
            query: 改写后的查询文本.
            keywords: 关键词列表（用于 MySQL 兜底）.
            city: 城市过滤.
            category: 类型过滤.
            n_results: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: spot 级结果，含 credibility_score / evidence。
        """
        try:
            from sqlalchemy import select, func, or_
            from src.models.spot import Spot
            from src.models.spot_doc import SpotDoc

            hits: List[Dict[str, Any]] = []

            # ---- 子路径 A：Chroma(spot_docs) 向量召回 ----
            chroma_available = await check_chroma_health()
            if chroma_available:
                try:
                    from src.services.rag.embeddings import embed_query_async
                    from src.services.rag.chroma_client import get_spot_docs_collection, run_sync

                    query_embedding = await embed_query_async(query)
                    collection = await get_spot_docs_collection()

                    def _do_query():
                        return collection.query(
                            query_embeddings=[query_embedding],
                            n_results=n_results,
                            include=["metadatas", "documents", "distances"],
                        )

                    results = await run_sync(_do_query)
                    if results and results.get("ids"):
                        for i in range(len(results["ids"][0])):
                            meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                            doc = results["documents"][0][i] if results.get("documents") else ""
                            dist = results["distances"][0][i] if results.get("distances") else 0.0
                            hits.append({
                                "spot_id": str(meta.get("spot_id")),
                                "source_type": meta.get("source_type"),
                                "source_name": meta.get("source_name"),
                                "source_url": meta.get("source_url"),
                                "content": doc,
                                "credibility_score": float(meta.get("credibility_score", 0.5)),
                                "score": 1.0 - dist,
                            })
                except Exception as e:
                    logger.warning("spot_docs Chroma 召回失败，尝试 MySQL 兜底", error=str(e))

            # ---- 子路径 B：MySQL LIKE(spot_docs) 兜底 / 补充 ----
            # 注：InnoDB FULLTEXT 对中文分词不可靠（min token / ngram），
            # Chroma 向量召回为主路径，MySQL 兜底用 LIKE（2 字窗口）保证可召回。
            if not hits:
                try:
                    seed = list(keywords) if keywords else []
                    seed += query.split()
                    seed = [t for t in seed if t]
                    terms = KnowledgeService._chinese_like_terms(seed) if seed else ([city] if city else [])
                    rows = []
                    if terms:
                        like_conds = [SpotDoc.content.like(f"%{t}%") for t in terms]
                        q = select(SpotDoc).where(or_(*like_conds))
                        if city:
                            q = q.join(Spot).where(Spot.city == city)
                        q = q.order_by(SpotDoc.credibility_score.desc()).limit(n_results)
                        rows = (await db.execute(q)).scalars().all()
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
                except Exception as e:
                    logger.warning("spot_docs MySQL 兜底召回失败", error=str(e))

            # 聚合到 spot 级：保留命中的 top-k 块作为证据（不再只取 1 块）。
            # 旧逻辑只保留「可信度最高」那 1 块，但同 spot 各块 credibility 相同
            # → 实际任取 1 块，长文其余切片仅贡献召回、不进证据。现改为按分数
            # 降序取前 N 块，全部拼进证据，让 LLM 看到完整切片。
            # 聚合逻辑抽到模块级 _aggregate_spot_docs，便于单测；此处仅调用。
            out = _aggregate_spot_docs(hits, max_chunks=3)

            logger.debug("spot_docs 召回完成", count=len(out))
            return out
        except Exception as e:
            logger.error("spot_docs 召回异常", error=str(e))
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

            # 构造 MATCH...AGAINST 查询（复合 FULLTEXT 索引 ft_name_desc）
            search_text = " ".join(keywords)

            query = select(Spot).where(
                text("MATCH(name, description) AGAINST (:q)").bindparams(q=search_text)
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

        含文本层真实证据片段，使 Cross-Encoder 拿到模型参数外的新信息，
        而非仅有 LLM 生成的描述。

        Args:
            spot: 景点字典（可能带 evidence 字段）.

        Returns:
            str: 文档文本.
        """
        tags = " ".join(spot.get("tags", [])) if isinstance(spot.get("tags"), list) else ""
        doc = f"{spot.get('city', '')} {spot.get('name', '')} {spot.get('description', '')} {tags} {spot.get('category', '')}"
        ev = spot.get("evidence")
        if isinstance(ev, dict) and ev.get("content"):
            doc += f" | 证据({ev.get('source_name', '')}): {ev.get('content', '')[:200]}"
        return doc

    @staticmethod
    async def bulk_import_spots(
        db: AsyncSession,
        spots_data: List[Dict[str, Any]],
        on_progress: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """批量导入景点（MySQL + ChromaDB 双写）。
        
        实现逻辑：
        - MySQL 批量 INSERT（batch insert）
        - ChromaDB 批量写入 embedding
        - 单条失败不阻断整批
        - 进度回调（可选）
        
        Args:
            db: 数据库会话
            spots_data: 景点数据列表
            on_progress: 进度回调函数（可选）
                signature: (completed: int, total: int, spot_name: str, ok: bool)
        
        Returns:
            {"success": int, "failed": int, "total": int, "errors": list}
        """
        import uuid
        from src.schemas.knowledge import SpotCreate
        
        total = len(spots_data)
        success = 0
        failed = 0
        errors = []
        
        # 收集待批量写入 Chroma 的数据
        chroma_ids = []
        chroma_embeddings = []
        chroma_documents = []
        chroma_metadatas = []
        
        for i, raw_data in enumerate(spots_data):
            spot_name = raw_data.get("name", f"unknown-{i}")
            try:
                # 验证数据
                validated = SpotCreate(**raw_data)
                vector_id = str(uuid.uuid4())
                
                # 创建 Spot 对象
                spot = Spot(
                    name=validated.name,
                    city=validated.city,
                    category=validated.category,
                    description=validated.description,
                    tags=validated.tags,
                    avg_cost=validated.avg_cost,
                    duration=validated.duration,
                    open_time=validated.open_time,
                    rating=validated.rating,
                    vector_id=vector_id,
                )
                db.add(spot)
                
                # 准备 Chroma 数据
                doc_text = build_embedding_document({
                    "city": validated.city,
                    "name": validated.name,
                    "description": validated.description,
                    "tags": validated.tags,
                    "category": validated.category,
                })
                chroma_ids.append(vector_id)
                chroma_documents.append(doc_text)
                chroma_metadatas.append({
                    "city": validated.city,
                    "name": validated.name,
                    "category": validated.category,
                    "tags": validated.tags if isinstance(validated.tags, str) else json.dumps(validated.tags, ensure_ascii=False),
                    "rating": validated.rating or 0,
                })
                
                success += 1
                
            except Exception as e:
                logger.error("景点导入失败", spot_name=spot_name, error=str(e))
                failed += 1
                errors.append({"name": spot_name, "error": str(e)})
            
            # 进度回调
            if on_progress:
                try:
                    on_progress(i + 1, total, spot_name, failed == 0 or i < success + failed - 1)
                except Exception:
                    pass
        
        # MySQL 批量提交
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("MySQL 批量提交失败", error=str(e))
            # 回滚所有成功计数
            return {"success": 0, "failed": total, "total": total, "errors": [{"name": "all", "error": str(e)}]}
        
        # 异步同步到 ChromaDB（每 spot 一个 job 入队，worker 异步消费）
        # 改造（M1）：原同步块"gather embeddings + 批量 add"是一次性提交，
        # 任一 spot 失败需要整批重试。改为细粒度入队：每 spot 一 job，
        # 失败单独重试，且 API 立即返回（不阻塞批量导入流程）。
        if chroma_ids:
            try:
                from src.services.tasks.chroma_sync import enqueue_bulk_chroma_sync

                await enqueue_bulk_chroma_sync(
                    vector_ids=chroma_ids,
                    doc_texts=chroma_documents,
                    metadatas=chroma_metadatas,
                )
                logger.info("ChromaDB 同步入队完成", count=len(chroma_ids))
            except Exception as e:
                logger.warning("ChromaDB 同步入队失败（MySQL 数据已保存）", error=str(e))
        
        logger.info("景点批量导入完成", success=success, failed=failed, total=total)
        return {"success": success, "failed": failed, "total": total, "errors": errors}

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
        # 给 LLM 的证据展示上限：单 spot 最多 EVIDENCE_MAX_CHUNKS 块，每块最多
        # EVIDENCE_CHUNK_DISPLAY_CHARS 字。search_spots 调用方 limit=5，最终 format
        # 通常只处理 5~10 个景点，证据体量有界（≈10 × 3 × 200 ≈ 6k 字），故放宽到
        # 200 字/块（与重排文档 _build_spot_document 的 200 一致），保留更完整的事实
        # 片段用于 grounding，而非截断到 120 字丢失约 60% 上下文。
        EVIDENCE_MAX_CHUNKS = 3
        EVIDENCE_CHUNK_DISPLAY_CHARS = 200

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
                # 文本层真实证据（多源异构 / 可信度 / 数据血缘）
                if spot.get("evidence"):
                    ev = spot["evidence"]
                    cred = ev.get("credibility_score", 0.0) or 0.0
                    chunks = ev.get("chunks")
                    if chunks:
                        # 多块证据：逐块展示（每块上限 EVIDENCE_CHUNK_DISPLAY_CHARS 字），最多 EVIDENCE_MAX_CHUNKS 块
                        for j, c in enumerate(chunks[:EVIDENCE_MAX_CHUNKS]):
                            cc = c.get("content") or ""
                            if len(cc) > EVIDENCE_CHUNK_DISPLAY_CHARS:
                                cc = cc[:EVIDENCE_CHUNK_DISPLAY_CHARS] + "..."
                            if j == 0:
                                lines.append(
                                    f"   - 来源片段（{ev.get('source_name', '')}，可信度 {cred:.2f}）：{cc}"
                                )
                            else:
                                lines.append(f"        › {cc}")
                    else:
                        content = ev.get("content") or ""
                        snippet = content[:80] + ("..." if len(content) > 80 else "")
                        lines.append(
                            f"   - 来源片段（{ev.get('source_name', '')}，可信度 {cred:.2f}）：{snippet}"
                        )
                    if ev.get("source_url"):
                        lines.append(f"   - 原文链接：{ev['source_url']}")

        return "\n".join(lines)
