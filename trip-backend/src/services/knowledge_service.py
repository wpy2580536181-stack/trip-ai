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
    vector_search_spots,
    vector_search_spot_docs,
    fulltext_search_spots,
    fulltext_search_spot_docs,
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
        # 1. Create spot
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
        )
        
        db.add(spot)
        await db.commit()
        await db.refresh(spot)
        
        # 2. 异步计算 embedding 并写入 PG
        try:
            from src.services.tasks.embedding_sync import enqueue_embedding_sync

            await enqueue_embedding_sync(
                spot_id=spot.id,
                city=spot.city,
                name=spot.name,
                description=spot.description,
                tags=spot.tags,
                category=spot.category,
                job_kind="create",
            )
            logger.info("Embedding sync enqueued", spot_id=spot.id, name=spot.name)
        except Exception as e:
            logger.warning("Embedding sync enqueue failed (PG data saved)", error=str(e))

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
        
        # 3. 异步重新计算 embedding
        try:
            from src.services.tasks.embedding_sync import enqueue_embedding_sync
        
            await enqueue_embedding_sync(
                spot_id=spot.id,
                city=spot.city,
                name=spot.name,
                description=spot.description,
                tags=spot.tags,
                category=spot.category,
                job_kind="update",
            )
            logger.info("Embedding sync (update) enqueued", spot_id=spot.id, name=spot.name)
        except Exception as e:
            logger.warning("Embedding sync enqueue failed (PG data updated)", error=str(e))

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
        
        # 2. Delete from PG (embedding 随行删除，无需额外操作)
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
        - 路径 1: pgvector spots 事实向量检索
        - 路径 2: pgvector spot_docs 文本向量召回（真实外部文本）
        - 路径 3: PostgreSQL tsvector 全文检索(spots)
        - 路径 4: 评分排序（基础召回）
        
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

            # 2. 四路顺序召回（SQLAlchemy async session 不支持同一 session 并发操作）
            # 每条路径独立超时，避免单一路径挂死拖慢整体
            path_pgvector: list = []
            path_docs: list = []
            path_pg_ft: list = []
            path_rating: list = []

            # pgvector / spot_docs 依赖 Embedding 模型（加载/推理不稳定），临时跳过
            for name, call in (
                ("rating", KnowledgeService._rating_search(db, city, category, limit * 2)),
                ("pg_fulltext", KnowledgeService._pg_fulltext_search(db, [query], city, category, limit * 2)),
            ):
                try:
                    result = await call
                    if name == "pg_fulltext":
                        path_pg_ft = result
                    elif name == "rating":
                        path_rating = result
                    logger.debug(f"召回路径 {name} 完成", count=len(result))
                except Exception as e:
                    logger.error(f"召回路径 {name} 失败", error=str(e))

            # 4. 融合（当前仅 rating + pg_fulltext 两条路径）
            paths = [path_pg_ft, path_rating]
            weights = [0.7, 0.5]
            try:
                fused = rrf_merge_with_weights(paths, weights, id_key="id", score_adjuster=weight_by_credibility)
            except Exception as e:
                logger.error("加权 RRF 失败，降级为普通 RRF", error=str(e))
                fused = rrf_merge(paths, id_key="id")
            logger.info("RRF 融合完成", fused_count=len(fused))

            if not fused:
                logger.warning("RRF 融合后无结果")
                return []

            # 当前仅 rating + pg_fulltext 两条路径，跳过 Cross-Encoder 重排（模型加载慢）
            final_items = fused[:limit]
            logger.info("RAG 检索完成", final_count=len(final_items))
            return final_items

        finally:
            if own_session:
                await db.close()

    @staticmethod
    async def _pgvector_search(
        db: AsyncSession,
        query: str,
        city: Optional[str] = None,
        category: Optional[str] = None,
        n_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """pgvector 向量检索 spots 表.

        Args:
            db: 数据库会话.
            query: 查询文本.
            city: 城市过滤.
            category: 类型过滤.
            n_results: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: 检索结果列表.
        """
        try:
            from src.services.rag.embeddings import embed_query_async

            query_embedding = await embed_query_async(query)
            return await vector_search_spots(
                db, query_embedding, city=city, category=category, limit=n_results
            )
        except Exception as e:
            logger.error("pgvector 检索失败", error=str(e))
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

        优先 pgvector 向量召回；失败时降级为 PG 全文检索。
        命中结果映射回 spot_id，返回 Spot 级结果并携带可信度与证据片段。

        Args:
            db: 数据库会话.
            query: 改写后的查询文本.
            keywords: 关键词列表（用于全文检索兜底）.
            city: 城市过滤.
            category: 类型过滤.
            n_results: 返回结果数量.

        Returns:
            List[Dict[str, Any]]: spot 级结果，含 credibility_score / evidence。
        """
        try:
            hits: List[Dict[str, Any]] = []

            # ---- 子路径 A：pgvector(spot_docs) 向量召回 ----
            try:
                from src.services.rag.embeddings import embed_query_async

                query_embedding = await embed_query_async(query)
                hits = await vector_search_spot_docs(
                    db, query_embedding, city=city, limit=n_results
                )
            except Exception as e:
                logger.warning("spot_docs pgvector 召回失败，尝试全文检索兜底", error=str(e))

            # ---- 子路径 B：PG 全文检索(spot_docs) 兜底 ----
            if not hits:
                try:
                    hits = await fulltext_search_spot_docs(
                        db, keywords, city=city, limit=n_results
                    )
                except Exception as e:
                    logger.warning("spot_docs PG 全文兜底召回失败", error=str(e))

            # 聚合到 spot 级
            out = _aggregate_spot_docs(hits, max_chunks=3)

            logger.debug("spot_docs 召回完成", count=len(out))
            return out
        except Exception as e:
            logger.error("spot_docs 召回异常", error=str(e))
            return []

    @staticmethod
    async def _pg_fulltext_search(
        db: AsyncSession,
        keywords: List[str],
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """PostgreSQL 全文检索 spots 表（委托给 fulltext_search 模块）."""
        return await fulltext_search_spots(db, keywords, city=city, category=category, limit=limit)

    @staticmethod
    async def _rating_search(
        db: AsyncSession,
        city: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """评分排序检索（基础召回）."""
        try:
            from sqlalchemy import text as _text
            sql = "SELECT id, name, city, category, description, rating, tags FROM spots"
            params: dict = {}
            clauses: list[str] = []
            if city:
                clauses.append("city = :city")
                params["city"] = city
            if category:
                clauses.append("category = :category")
                params["category"] = category
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY rating DESC NULLS LAST LIMIT :limit"
            params["limit"] = limit

            result = await db.execute(_text(sql), params)
            rows = result.fetchall()

            spot_dicts = []
            for row in rows:
                spot_dicts.append({
                    "id": str(row.id),
                    "name": row.name,
                    "city": row.city,
                    "category": row.category,
                    "description": row.description,
                    "rating": row.rating or 0,
                    "tags": row.tags,
                    "_source": "rating",
                })

            logger.debug("评分检索完成", count=len(spot_dicts))
            return spot_dicts
        except Exception as e:
            logger.error("评分检索失败", error=str(e))
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
        """批量导入景点（PostgreSQL + pgvector）。
            
        实现逻辑：
        - PG 批量 INSERT
        - 异步入队计算 embedding 写入 embedding 列
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
        from src.schemas.knowledge import SpotCreate
            
        total = len(spots_data)
        success = 0
        failed = 0
        errors = []
            
        # 收集待计算 embedding 的 spot 信息
        pending_embeddings: List[Dict[str, Any]] = []
            
        for i, raw_data in enumerate(spots_data):
            spot_name = raw_data.get("name", f"unknown-{i}")
            try:
                # 验证数据
                validated = SpotCreate(**raw_data)
                    
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
                )
                db.add(spot)
                await db.flush()  # 获取 spot.id
                    
                # 记录待计算 embedding
                pending_embeddings.append({
                    "spot_id": spot.id,
                    "city": validated.city,
                    "name": validated.name,
                    "description": validated.description,
                    "tags": validated.tags,
                    "category": validated.category,
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
            
        # PG 批量提交
        try:
            await db.commit()
        except Exception as e:
            await db.rollback()
            logger.error("PG 批量提交失败", error=str(e))
            return {"success": 0, "failed": total, "total": total, "errors": [{"name": "all", "error": str(e)}]}
            
        # 异步入队计算 embedding
        if pending_embeddings:
            try:
                from src.services.tasks.embedding_sync import enqueue_bulk_embedding_sync
    
                await enqueue_bulk_embedding_sync(pending_embeddings)
                logger.info("Embedding 同步入队完成", count=len(pending_embeddings))
            except Exception as e:
                logger.warning("Embedding 同步入队失败（PG 数据已保存）", error=str(e))
        
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


# 模块级别名：retrieve_knowledge_tool 通过 from ... import search_spots 导入
search_spots = KnowledgeService.search_spots
