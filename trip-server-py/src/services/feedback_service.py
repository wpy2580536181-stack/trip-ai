"""Feedback service (business logic)"""

from sqlalchemy import select, func, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from datetime import datetime, timedelta, date, timezone
import logging

from src.models.feedback import Feedback
from src.models.message import Message
from src.models.conversation import Conversation
from src.models.user import User
from src.schemas.user import FeedbackCreate, FeedbackResponse

log = logging.getLogger(__name__)


class FeedbackService:
    """Feedback service class"""
    
    @staticmethod
    async def get_user_feedbacks(
        db: AsyncSession,
        user_id: int,
        page: int = 1,
        page_size: int = 20
    ) -> dict:
        """获取用户的反馈列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            page: 页码
            page_size: 每页条数
            
        Returns:
            dict: 包含反馈列表和分页信息的响应
        """
        # 计算偏移量
        offset = (page - 1) * page_size
        
        # 查询总数
        count_stmt = select(func.count()).where(Feedback.user_id == user_id)
        count_result = await db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 查询反馈列表
        stmt = select(Feedback).where(
            Feedback.user_id == user_id
        ).order_by(
            Feedback.created_at.desc()
        ).offset(offset).limit(page_size)
        
        result = await db.execute(stmt)
        feedbacks = result.scalars().all()
        
        return {
            "items": [
                {
                    "id": f.id,
                    "messageId": f.message_id,
                    "conversationId": f.conversation_id,
                    "rating": f.rating,
                    "comment": f.comment,
                    "tags": f.tags,
                    "createdAt": f.created_at.isoformat()
                }
                for f in feedbacks
            ],
            "total": total,
            "page": page,
            "pageSize": page_size
        }
    
    @staticmethod
    async def submit_feedback(
        db: AsyncSession,
        user_id: int,
        data: FeedbackCreate
    ) -> dict:
        """提交反馈
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            data: 反馈数据
            
        Returns:
            dict: 反馈记录
        """
        # 防滥用：截断 comment 和 tags
        safe_comment = (data.comment or "")[:500] if data.comment else None
        safe_tags = None
        if data.tags and len(data.tags) > 0:
            safe_tags = [t[:50] for t in data.tags[:10]]

        # IDOR 防护：验证 message 存在
        msg_stmt = select(Message).where(Message.id == data.message_id)
        msg_result = await db.execute(msg_stmt)
        message = msg_result.scalar_one_or_none()
        if not message:
            raise ValueError("消息不存在")

        # 只能对 assistant 角色的消息评分
        if message.role != "assistant":
            raise ValueError("只能对 agent 回复评分")

        # 验证 message 所属 conversation 属于当前用户
        conv_stmt = select(Conversation).where(Conversation.id == data.conversation_id)
        conv_result = await db.execute(conv_stmt)
        conversation = conv_result.scalar_one_or_none()
        if not conversation:
            raise ValueError("对话不存在")
        if conversation.user_id != user_id:
            raise PermissionError("无权操作其他用户的反馈")

        # 检查是否已存在反馈
        stmt = select(Feedback).where(
            Feedback.user_id == user_id,
            Feedback.message_id == data.message_id
        )
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新现有反馈
            existing.rating = data.rating
            existing.comment = safe_comment
            existing.tags = safe_tags
            await db.commit()
            await db.refresh(existing)
            return {
                "id": existing.id,
                "rating": existing.rating
            }
        
        # 创建新反馈
        feedback = Feedback(
            user_id=user_id,
            message_id=data.message_id,
            conversation_id=data.conversation_id,
            rating=data.rating,
            comment=safe_comment,
            tags=safe_tags
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        
        return {
            "id": feedback.id,
            "rating": feedback.rating
        }
    
    @staticmethod
    async def get_message_stats(
        db: AsyncSession,
        message_id: int
    ) -> dict:
        """获取消息反馈统计
        
        Args:
            db: 数据库会话
            message_id: 消息ID
            
        Returns:
            dict: 统计信息
        """
        stmt = select(
            func.count(case((Feedback.rating == 1, 1))).label("up"),
            func.count(case((Feedback.rating == -1, 1))).label("down"),
            func.count().label("total")
        ).where(Feedback.message_id == message_id)
        
        result = await db.execute(stmt)
        row = result.one()
        
        up = row.up or 0
        down = row.down or 0
        total = row.total or 0
        satisfaction_rate = (up / total * 100) if total > 0 else None
        
        return {
            "up": up,
            "down": down,
            "total": total,
            "satisfactionRate": satisfaction_rate
        }
    
    @staticmethod
    async def get_global_stats(
        db: AsyncSession,
        days: int = 7
    ) -> dict:
        """获取全局反馈统计
        
        Args:
            db: 数据库会话
            days: 统计天数
            
        Returns:
            dict: 统计信息
        """
        from datetime import datetime, timedelta, timezone
        
        since = datetime.now(timezone.utc) - timedelta(days=days)
        
        stmt = select(
            func.count().label("total_count"),
            func.count(case((Feedback.rating == 1, 1))).label("up_count"),
            func.count(case((Feedback.rating == -1, 1))).label("down_count")
        ).where(Feedback.created_at >= since)
        
        result = await db.execute(stmt)
        row = result.one()
        
        total_count = row.total_count or 0
        up_count = row.up_count or 0
        down_count = row.down_count or 0
        satisfaction_rate = (up_count / total_count * 100) if total_count > 0 else 0
        
        # 获取最近的负面评论
        recent_down_stmt = select(Feedback).where(
            Feedback.rating == -1,
            Feedback.created_at >= since
        ).order_by(Feedback.created_at.desc()).limit(20)
        
        recent_result = await db.execute(recent_down_stmt)
        recent_down = [
            {
                "comment": f.comment,
                "tags": f.tags,
                "createdAt": f.created_at.isoformat()
            }
            for f in recent_result.scalars().all()
        ]
        
        return {
            "totalCount": total_count,
            "upCount": up_count,
            "downCount": down_count,
            "satisfactionRate": satisfaction_rate,
            "recentDownComments": recent_down
        }
    
    @staticmethod
    async def list_for_message(
        db: AsyncSession,
        message_id: int
    ) -> list[dict]:
        """列出某条消息的所有反馈（admin 调试用）
        
        Args:
            db: 数据库会话
            message_id: 消息ID
            
        Returns:
            list[dict]: 反馈列表
        """
        stmt = (
            select(Feedback, User.id.label("user_id"), User.username)
            .join(User, Feedback.user_id == User.id)
            .where(Feedback.message_id == message_id)
            .order_by(Feedback.created_at.desc())
        )
        result = await db.execute(stmt)
        rows = result.all()
        
        return [
            {
                "id": row.Feedback.id,
                "messageId": row.Feedback.message_id,
                "conversationId": row.Feedback.conversation_id,
                "rating": row.Feedback.rating,
                "comment": row.Feedback.comment,
                "tags": row.Feedback.tags,
                "user": {"id": row.user_id, "username": row.username},
                "createdAt": row.Feedback.created_at.isoformat()
            }
            for row in rows
        ]

    @staticmethod
    async def get_high_token_low_satisfaction(
        db: AsyncSession,
        since_days: int = 7,
        limit: int = 20
    ) -> list[dict]:
        """高 token + 低满意度案例（admin dashboard 用）
        
        找出负反馈（rating=-1）的 message，关联 message.metadata.usage，
        按 token 总数降序返回 top N。
        
        Args:
            db: 数据库会话
            since_days: 查询最近天数
            limit: 返回条数上限
            
        Returns:
            list[dict]: 高 token 低满意度案例列表
        """
        since = datetime.now(timezone.utc) - timedelta(days=since_days)

        # 获取负反馈（多取一些，后续过滤排序）
        fb_stmt = (
            select(Feedback, User.id.label("user_id"), User.username, User.nickname)
            .join(User, Feedback.user_id == User.id)
            .where(Feedback.created_at >= since, Feedback.rating == -1)
            .order_by(Feedback.created_at.desc())
            .limit(200)
        )
        fb_result = await db.execute(fb_stmt)
        fb_rows = fb_result.all()

        if not fb_rows:
            return []

        # 关联 message 的 metadata.usage
        message_ids = list({row.Feedback.message_id for row in fb_rows})
        msg_stmt = select(Message).where(Message.id.in_(message_ids))
        msg_result = await db.execute(msg_stmt)
        msg_map = {m.id: m for m in msg_result.scalars().all()}

        cases = []
        for row in fb_rows:
            fb = row.Feedback
            msg = msg_map.get(fb.message_id)
            if not msg:
                continue
            meta = msg.metadata_ or {}
            u = meta.get("usage") if isinstance(meta, dict) else None
            usage = None
            if u and isinstance(u, dict):
                prompt = u.get("prompt", 0) or 0
                cached = u.get("cached", 0) or 0
                usage = {
                    "prompt": prompt,
                    "completion": u.get("completion", 0) or 0,
                    "total": u.get("total", 0) or 0,
                    "cached": cached,
                    "cacheHitRate": cached / prompt if prompt > 0 else 0,
                }
            tags_val = fb.tags
            cases.append({
                "feedbackId": fb.id,
                "messageId": fb.message_id,
                "rating": fb.rating,
                "comment": fb.comment,
                "tags": tags_val if isinstance(tags_val, list) else None,
                "user": {"id": row.user_id, "username": row.username, "nickname": row.nickname},
                "messagePreview": (msg.content or "")[:200],
                "usage": usage,
                "createdAt": fb.created_at.isoformat(),
            })

        # 按 token 总数降序，无 usage 的排最后
        cases.sort(key=lambda c: (c["usage"] or {}).get("total", -1), reverse=True)
        return cases[:limit]

    @staticmethod
    async def get_daily_stats(
        db: AsyncSession,
        start_date: date,
        end_date: date
    ) -> list[dict]:
        """日维度统计（admin dashboard 趋势图）
        按日期分组统计反馈数据，含日期填充确保连续日期无间断。
        
        Args:
            db: 数据库会话
            start_date: 起始日期
            end_date: 结束日期
            
        Returns:
            list[dict]: 每日统计数据
        """
        # 使用原生 SQL 做 GROUP BY DATE（SQLAlchemy 跨 dialect 兼容性有限）
        sql = text("""
            SELECT
                DATE(created_at) AS date,
                SUM(CASE WHEN rating = 1 THEN 1 ELSE 0 END) AS up,
                SUM(CASE WHEN rating = -1 THEN 1 ELSE 0 END) AS down
            FROM feedbacks
            WHERE created_at >= :start_date
              AND created_at < :end_date_exclusive
            GROUP BY DATE(created_at)
            ORDER BY date ASC
        """)
        end_date_exclusive = end_date + timedelta(days=1)
        result = await db.execute(sql, {
            "start_date": start_date.isoformat(),
            "end_date_exclusive": end_date_exclusive.isoformat(),
        })
        rows = result.all()

        # 构建日期 -> 数据映射
        row_map = {}
        for r in rows:
            d = r.date if isinstance(r.date, str) else r.date.isoformat()
            row_map[d] = {"up": int(r.up or 0), "down": int(r.down or 0)}

        # 填充缺失日期
        output = []
        current = start_date
        while current <= end_date:
            key = current.isoformat()
            entry = row_map.get(key, {"up": 0, "down": 0})
            up = entry["up"]
            down = entry["down"]
            total = up + down
            output.append({
                "date": key,
                "up": up,
                "down": down,
                "total": total,
                "satisfactionRate": up / total if total > 0 else 0,
            })
            current += timedelta(days=1)

        return output

    @staticmethod
    async def convert_to_fixture(
        db: AsyncSession,
        feedback_ids: list[int]
    ) -> dict:
        """转换反馈为测试夹具
        
        Args:
            db: 数据库会话
            feedback_ids: 反馈ID列表
            
        Returns:
            dict: 转换结果 {files, skipped}
        """
        # 输入验证
        if not isinstance(feedback_ids, list) or len(feedback_ids) == 0:
            raise ValueError("feedbackIds 必填且为非空数组")
        if len(feedback_ids) > 50:
            raise ValueError("最多 50 条")

        files: list[str] = []
        skipped: list[dict] = []
        for fid in feedback_ids:
            try:
                # TODO: 实现单条转换逻辑
                skipped.append({"id": fid, "reason": "Not implemented yet"})
            except Exception as e:
                skipped.append({"id": fid, "reason": str(e)})

        return {
            "files": files,
            "skipped": skipped
        }
