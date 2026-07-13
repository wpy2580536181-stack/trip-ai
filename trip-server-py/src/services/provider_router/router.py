"""Provider Router — 智能路由选择。

根据场景选择 provider：
- planning → DeepSeek（强推理）
- chat → 最便宜的健康 provider（Agnes）
- research → 最低延迟 provider
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Optional

from src.config.llm import (
    load_llm_config_for_provider,
    create_llm_from_config,
)
from src.services.provider_router.health import ProviderStatus, provider_health

logger = logging.getLogger(__name__)


class Scenario(str, Enum):
    PLANNING = "planning"        # 行程规划（需要强推理能力）
    CHAT = "chat"                # 简单对话（优先低成本）
    RESEARCH = "research"        # 情报检索等简单工具调用


# Provider 优先级（按场景）
SCENARIO_PRIORITY: dict[Scenario, list[str]] = {
    Scenario.PLANNING: ["deepseek", "kimi", "agnese"],
    Scenario.CHAT: ["agnese", "kimi", "deepseek"],
    Scenario.RESEARCH: ["agnese", "deepseek", "kimi"],
}


def select_provider(scenario: Scenario) -> str:
    """根据场景选择最优 provider。"""
    priority = SCENARIO_PRIORITY.get(scenario, ["deepseek"])
    healthy = provider_health.get_healthy_providers()

    for p in priority:
        if p in healthy:
            logger.info("provider_router|selected provider=%s scenario=%s", p, scenario.value)
            return p

    # 所有 provider 都不可用，尝试最优先的
    fallback = priority[0]
    logger.warning("provider_router|no_healthy_provider scenario=%s fallback=%s", scenario.value, fallback)
    return fallback


async def call_with_fallback(
    scenario: Scenario,
    primary_fn,         # 主 provider 的 LLM 调用函数
    fallback_fn,        # 备用 provider 的 LLM 调用函数（可选）
    timeout_s: float = 15.0,
) -> tuple[str, str]:
    """使用主 provider 调用，超时或失败时启用 fallback。

    如果主 provider 在 timeout_s 内无响应，则并发启动 fallback，
    取最先返回的结果。
    """
    primary_name = select_provider(scenario)
    t0 = time.time()

    try:
        result = await asyncio.wait_for(primary_fn(), timeout=timeout_s)
        latency_ms = (time.time() - t0) * 1000
        provider_health.record_success(primary_name, latency_ms)
        return result, primary_name
    except asyncio.TimeoutError:
        logger.warning("provider_router|timeout provider=%s scenario=%s", primary_name, scenario.value)
        provider_health.record_failure(primary_name)

        # 超时后尝试 fallback
        if fallback_fn:
            fallback_name = select_provider(scenario)
            if fallback_name != primary_name:
                logger.info("provider_router|fallback_to provider=%s", fallback_name)
                try:
                    result = await fallback_fn()
                    latency_ms = (time.time() - t0) * 1000
                    provider_health.record_success(fallback_name, latency_ms)
                    return result, fallback_name
                except Exception as e:
                    provider_health.record_failure(fallback_name)
                    raise

        raise  # 无 fallback → 透传超时异常

    except Exception as e:
        provider_health.record_failure(primary_name)
        if fallback_fn:
            fallback_name = select_provider(scenario)
            if fallback_name != primary_name:
                try:
                    result = await fallback_fn()
                    latency_ms = (time.time() - t0) * 1000
                    provider_health.record_success(fallback_name, latency_ms)
                    return result, fallback_name
                except Exception:
                    provider_health.record_failure(fallback_name)
        raise


def create_scenario_llm(scenario: Scenario):
    """创建指定场景的 LLM 实例。"""
    provider = select_provider(scenario)
    cfg = load_llm_config_for_provider(provider)
    if not cfg:
        logger.warning("provider_router|config_missing provider=%s scenario=%s, falling back to deepseek", provider, scenario.value)
        cfg = load_llm_config_for_provider("deepseek")
    if not cfg:
        raise ValueError("No valid LLM provider configuration found")
    return create_llm_from_config(cfg)
