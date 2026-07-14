"""
告警检测器

查过去 N 分钟 feedback，计算 satisfactionRate，判断是否低于阈值。
阈值判断逻辑：
  - 反馈数 >= min_feedbacks（防样本太少误报）
  - satisfaction_rate < threshold
两个条件都满足才告警。
"""

from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from typing import Optional
import logging

from src.models.feedback import Feedback
from src.config.settings import settings

log = logging.getLogger("alert")


@dataclass
class AlertCheckResult:
    """告警检测结果"""
    should_alert: bool
    reason: str
    stats: dict
    threshold: float
    min_feedbacks: int


class AlertDetector:
    """告警检测器"""

    async def check(self, db: AsyncSession) -> AlertCheckResult:
        """
        检测是否需要发送告警
        
        Args:
            db: 数据库会话
            
        Returns:
            AlertCheckResult: 检测结果
        """
        window_minutes = settings.alert_window_minutes
        threshold = settings.alert_threshold
        min_feedbacks = settings.alert_min_feedbacks
        
        since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)

        # 统计正面和负面反馈
        stmt = select(
            func.count(case((Feedback.rating == 1, 1))).label("up"),
            func.count(case((Feedback.rating == -1, 1))).label("down"),
        ).where(Feedback.created_at >= since)
        
        result = await db.execute(stmt)
        row = result.one()
        
        up = row.up or 0
        down = row.down or 0
        total = up + down
        rate = up / total if total > 0 else 0

        # 获取最近的负面评论
        recent_down_stmt = select(Feedback).where(
            Feedback.rating == -1,
            Feedback.created_at >= since,
            Feedback.comment.isnot(None)
        ).order_by(Feedback.created_at.desc()).limit(5)
        
        recent_result = await db.execute(recent_down_stmt)
        recent_down_feedbacks = recent_result.scalars().all()
        
        recent_down_comments = [
            {
                "comment": f.comment or "",
                "tags": f.tags if isinstance(f.tags, list) else None,
                "createdAt": f.created_at.isoformat()
            }
            for f in recent_down_feedbacks
        ]

        # 判断是否需要告警
        should_alert = total >= min_feedbacks and rate < threshold

        if should_alert:
            reason = f"过去 {window_minutes} 分钟 {total} 条反馈，满意率 {rate * 100:.1f}% < {threshold * 100:.0f}%"
        elif total < min_feedbacks:
            reason = f"样本不足：{total}/{min_feedbacks} 反馈"
        else:
            reason = f"正常：{total} 条反馈，满意率 {rate * 100:.1f}%"

        log.debug(f"告警检测: should_alert={should_alert}, total={total}, rate={rate:.2f}, reason={reason}")

        return AlertCheckResult(
            should_alert=should_alert,
            reason=reason,
            stats={
                "feedbackCount": total,
                "upCount": up,
                "downCount": down,
                "satisfactionRate": rate,
                "recentDownComments": recent_down_comments,
            },
            threshold=threshold,
            min_feedbacks=min_feedbacks,
        )


# 单例
alert_detector = AlertDetector()
