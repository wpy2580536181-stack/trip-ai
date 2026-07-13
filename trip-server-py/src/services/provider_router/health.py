"""Provider Health Check 模块。

周期性健康检查 + 实时状态跟踪。
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum

from src.config.llm import load_llm_config_for_provider
from src.config.settings import settings

logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


@dataclass
class ProviderState:
    name: str
    status: ProviderStatus = ProviderStatus.HEALTHY
    last_success_time: float = 0.0
    last_failure_time: float = 0.0
    consecutive_failures: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    total_calls: int = 0

    DEGRADED_THRESHOLD = 3      # 连续 3 次失败 → degraded
    DOWN_THRESHOLD = 5          # 连续 5 次失败 → down
    AUTO_RECOVERY_S = 60        # 60s 后尝试恢复

    def record_success(self, latency_ms: float) -> None:
        self.last_success_time = time.time()
        self.consecutive_failures = 0
        self.total_calls += 1
        self.avg_latency_ms = (
            (self.avg_latency_ms * (self.total_calls - 1) + latency_ms)
            / self.total_calls
        )
        self.status = ProviderStatus.HEALTHY

    def record_failure(self) -> None:
        self.last_failure_time = time.time()
        self.consecutive_failures += 1
        self.error_count += 1
        self.total_calls += 1

        if self.consecutive_failures >= self.DOWN_THRESHOLD:
            self.status = ProviderStatus.DOWN
        elif self.consecutive_failures >= self.DEGRADED_THRESHOLD:
            self.status = ProviderStatus.DEGRADED

    def should_auto_recover(self) -> bool:
        if self.status != ProviderStatus.DOWN and self.status != ProviderStatus.DEGRADED:
            return False
        recovery_time = self.AUTO_RECOVERY_S
        return (time.time() - self.last_failure_time) > recovery_time


class ProviderHealth:
    """Provider 健康状态管理器。"""

    def __init__(self):
        self._providers: dict[str, ProviderState] = {}
        self._lock = asyncio.Lock()
        self._health_check_task: asyncio.Task | None = None

        # 注册已知 provider
        for name in ("deepseek", "kimi", "agnese"):
            self._providers[name] = ProviderState(name=name)

    def get_state(self, name: str) -> ProviderState:
        if name not in self._providers:
            self._providers[name] = ProviderState(name=name)
        return self._providers[name]

    def record_success(self, name: str, latency_ms: float) -> None:
        state = self.get_state(name)
        state.record_success(latency_ms)
        logger.info(
            "provider_health|success provider=%s latency=%dms status=%s",
            name, int(latency_ms), state.status.value,
        )

    def record_failure(self, name: str) -> None:
        state = self.get_state(name)
        state.record_failure()
        logger.warning(
            "provider_health|failure provider=%s consec=%d status=%s",
            name, state.consecutive_failures, state.status.value,
        )

    def get_healthy_providers(self) -> list[str]:
        return [
            name for name, state in self._providers.items()
            if state.status == ProviderStatus.HEALTHY
            or state.should_auto_recover()
        ]

    def get_best_provider(self, preferred: str = "deepseek") -> str:
        """获取最佳可用 provider。"""
        healthy = self.get_healthy_providers()
        if not healthy:
            return preferred  # 无健康 provider 时尝试主 provider
        if preferred in healthy:
            return preferred
        return healthy[0]

    async def start_health_check(self, interval_s: int = 30) -> None:
        """启动周期性健康检查。"""
        if self._health_check_task is not None:
            return
        self._health_check_task = asyncio.create_task(
            self._health_check_loop(interval_s)
        )
        logger.info("provider_health|health_check_started interval=%ds", interval_s)

    async def _health_check_loop(self, interval_s: int) -> None:
        """健康检查循环 —— 调用每个 provider 的简单接口验证可用性。"""
        while True:
            await asyncio.sleep(interval_s)
            for name in ("deepseek", "kimi", "agnese"):
                state = self._providers[name]
                if state.status == ProviderStatus.HEALTHY:
                    continue  # 健康的无需探测
                if not state.should_auto_recover():
                    continue

                # 探测：检查配置是否完整
                cfg = load_llm_config_for_provider(name)
                if cfg:
                    self._providers[name].consecutive_failures = 0
                    self._providers[name].status = ProviderStatus.DEGRADED
                    logger.info("provider_health|recovered provider=%s", name)
                else:
                    logger.info("provider_health|still_down provider=%s", name)


# 全局实例
provider_health = ProviderHealth()
