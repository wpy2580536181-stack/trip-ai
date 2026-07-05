"""
告警去重器

基于告警类型+关键信息的指纹去重。
冷却期内相同告警不重复发送。
支持内存存储（dict + TTL），可选 Redis。
"""

import time
import hashlib
from typing import Optional
import logging

from src.config.settings import settings

log = logging.getLogger("alert")


class AlertDeduplicator:
    """告警去重器（内存模式）"""

    def __init__(self):
        # 内存存储：{fingerprint: expire_timestamp}
        self._store: dict[str, float] = {}

    def _fingerprint(self, alert_type: str, key_info: str = "") -> str:
        """
        生成告警指纹
        
        Args:
            alert_type: 告警类型
            key_info: 关键信息
            
        Returns:
            str: 指纹哈希
        """
        raw = f"{alert_type}:{key_info}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cleanup_expired(self) -> None:
        """清理过期的指纹记录"""
        now = time.time()
        expired_keys = [k for k, v in self._store.items() if v < now]
        for k in expired_keys:
            del self._store[k]

    async def should_send(self, alert_type: str = "feedback_low", key_info: str = "") -> bool:
        """
        判断是否应该发送告警（未被去重）
        
        Args:
            alert_type: 告警类型
            key_info: 关键信息
            
        Returns:
            bool: True 表示应该发送
        """
        self._cleanup_expired()
        fingerprint = self._fingerprint(alert_type, key_info)
        return fingerprint not in self._store

    async def mark_sent(self, alert_type: str = "feedback_low", key_info: str = "") -> None:
        """
        标记告警已发送
        
        Args:
            alert_type: 告警类型
            key_info: 关键信息
        """
        fingerprint = self._fingerprint(alert_type, key_info)
        cooldown = settings.alert_cooldown_seconds
        self._store[fingerprint] = time.time() + cooldown
        log.debug(f"告警已标记: fingerprint={fingerprint[:8]}..., cooldown={cooldown}s")

    def clear(self) -> None:
        """清空所有记录（测试用）"""
        self._store.clear()


# 单例
alert_deduplicator = AlertDeduplicator()
