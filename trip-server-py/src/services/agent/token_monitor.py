"""Token Monitor 模块。

使用环形缓冲区记录 Token 使用量，用于监控和告警。
"""

from collections import deque
from typing import Optional
import time


# 环形缓冲区大小
MAX_RECORDS = 1000

# 告警阈值（可配置）
TOKEN_ALERT_THRESHOLD = 100_000  # 单次请求超过 100K token 告警


class TokenMonitor:
    """Token 使用量监控器（环形缓冲区）。
    
    记录每次 Agent 请求的 Token 消耗，
    支持阈值告警和统计分析。
    """
    
    def __init__(self, max_records: int = MAX_RECORDS):
        """初始化 TokenMonitor。
        
        Args:
            max_records: 环形缓冲区大小
        """
        self.max_records = max_records
        self._records: deque = deque(maxlen=max_records)
        self._alert_threshold = TOKEN_ALERT_THRESHOLD
    
    def record(self, record: dict) -> None:
        """记录一条 Token 使用量记录。
        
        Args:
            record: 记录字典，包含：
                - request_type: 请求类型（chat/recommend）
                - route: 路由结果（planning/general）
                - user_id: 用户 ID
                - conversation_id: 对话 ID
                - message_id: 消息 ID
                - total_usage: Token 使用量 {"prompt": N, "completion": N, "total": N, "cached": N}
                - latency_ms: 延迟毫秒数
                - timestamp: 时间戳（毫秒）
        """
        # 添加记录
        self._records.append(record)
        
        # 检查告警阈值
        total_usage = record.get("total_usage", {})
        total_tokens = total_usage.get("total", 0)
        
        if total_tokens > self._alert_threshold:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Token 使用量超限: {total_tokens} > {self._alert_threshold}",
                extra={
                    "user_id": record.get("user_id"),
                    "request_type": record.get("request_type"),
                    "total_tokens": total_tokens,
                },
            )
    
    def get_recent(self, limit: int = 100) -> list[dict]:
        """获取最近的 N 条记录。
        
        Args:
            limit: 返回记录数上限
            
        Returns:
            记录列表（按时间倒序）
        """
        records = list(self._records)
        return records[-limit:][::-1]  # 倒序
    
    def get_stats(self, time_window_ms: Optional[int] = None) -> dict:
        """获取统计信息。
        
        Args:
            time_window_ms: 时间窗口（毫秒），None 表示全部
            
        Returns:
            统计信息字典
        """
        records = list(self._records)
        
        # 过滤时间窗口
        if time_window_ms is not None:
            current_time = int(time.time() * 1000)
            start_time = current_time - time_window_ms
            records = [r for r in records if r.get("timestamp", 0) >= start_time]
        
        if not records:
            return {
                "count": 0,
                "avg_total": 0,
                "max_total": 0,
                "min_total": 0,
            }
        
        # 计算统计
        totals = [r.get("total_usage", {}).get("total", 0) for r in records]
        
        return {
            "count": len(records),
            "avg_total": sum(totals) / len(totals),
            "max_total": max(totals),
            "min_total": min(totals),
        }
    
    def clear(self) -> None:
        """清空记录。"""
        self._records.clear()


# 全局单例
token_monitor = TokenMonitor()
