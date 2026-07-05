"""
告警调度器

使用 asyncio 定时任务（如每 5 分钟检测一次）
在应用启动时启动，关闭时停止
调度流程：detect → deduplicate → send

tick() 单独暴露，方便测试和手动触发
"""

import asyncio
from typing import Optional
import logging

from src.config.settings import settings
from src.config.database import async_session
from src.services.alert.alert_detector import alert_detector
from src.services.alert.alert_deduplicator import alert_deduplicator
from src.services.alert.alert_webhook import webhook_notifier

log = logging.getLogger("alert")


class AlertScheduler:
    """告警调度器"""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def start(self) -> None:
        """启动调度器"""
        if not settings.alert_enabled:
            log.info("告警调度未启用（ALERT_ENABLED=false）")
            return
        
        if not settings.alert_webhook_url:
            log.warning("ALERT_ENABLED=true 但 ALERT_WEBHOOK_URL 未配置，调度器不启动")
            return
        
        if self._running:
            log.warning("告警调度器已在运行")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        
        interval = settings.alert_interval_seconds
        log.info(
            f"告警调度已启动: interval={interval}s, type={settings.alert_webhook_type}, "
            f"threshold={settings.alert_threshold}, min_feedbacks={settings.alert_min_feedbacks}, "
            f"window={settings.alert_window_minutes}min"
        )

    def stop(self) -> None:
        """停止调度器"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
            log.info("告警调度已停止")

    async def _run_loop(self) -> None:
        """调度循环"""
        interval = settings.alert_interval_seconds
        
        while self._running:
            try:
                await self.tick()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error(f"tick 异常: {e}")
            
            try:
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break

    async def tick(self) -> dict:
        """
        执行一次检测（可手动触发）
        
        Returns:
            dict: {"shouldAlert": bool, "sent": bool, "reason": str}
        """
        async with async_session() as db:
            check = await alert_detector.check(db)
        
        if not check.should_alert:
            log.debug(f"告警检查：正常，无需发送 - {check.reason}")
            return {"shouldAlert": False, "sent": False, "reason": check.reason}

        # 去重检查
        if not await alert_deduplicator.should_send():
            log.info(f"告警已被去重（冷却期内已发送）- {check.reason}")
            return {"shouldAlert": True, "sent": False, "reason": check.reason}

        # 发送通知
        result = await webhook_notifier.send(check)
        if result.success:
            await alert_deduplicator.mark_sent()
            log.info(f"告警已发送: attempts={result.attempts}, reason={check.reason}")
            return {"shouldAlert": True, "sent": True, "reason": check.reason}
        
        log.error(f"告警发送失败: error={result.error}, attempts={result.attempts}, reason={check.reason}")
        return {"shouldAlert": True, "sent": False, "reason": check.reason}


# 单例
alert_scheduler = AlertScheduler()
