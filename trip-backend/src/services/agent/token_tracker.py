"""Token Tracker — LangChain callback 集成。

对齐 Node.js 版 `llmGuard/tokenTracker.ts`：
- 每次 LLM 调用结束后提取 token 用量
- 通过 contextvars 维护 userId / endpoint 上下文
- 写入 TokenUsageLog（经 token_monitor）并更新 token_budget_manager
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from typing import Any, Optional

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 上下文变量（对齐 Node.js AsyncLocalStorage<llmContext>）
# ---------------------------------------------------------------------------

llm_user_id: contextvars.ContextVar[int] = contextvars.ContextVar("llm_user_id", default=0)
llm_endpoint: contextvars.ContextVar[str] = contextvars.ContextVar("llm_endpoint", default="background")


class LLMContext:
    """Context manager 辅助类，设置 / 恢复 llm_user_id 和 llm_endpoint。"""

    def __init__(self, user_id: int | str = 0, endpoint: str = "background"):
        self._user_id = int(user_id) if user_id else 0
        self._endpoint = endpoint
        self._tokens: list[contextvars.Token] = []

    def __enter__(self) -> "LLMContext":
        self._tokens.append(llm_user_id.set(self._user_id))
        self._tokens.append(llm_endpoint.set(self._endpoint))
        return self

    def __exit__(self, *exc: Any) -> None:
        for tok in reversed(self._tokens):
            tok.var.reset(tok)
        self._tokens.clear()


# ---------------------------------------------------------------------------
# 内部：记录用量
# ---------------------------------------------------------------------------


def _record_usage(prompt: int, completion: int, cached: int = 0) -> None:
    """记录一次 LLM 调用的 token 用量。

    - 写入 token_monitor（持久化到 DB）
    - 更新 token_budget_manager（内存计数器）
    """
    user_id = llm_user_id.get()
    endpoint = llm_endpoint.get()
    total = prompt + completion

    # 1. 写入 token_monitor（异步，用 fire-and-forget task）
    try:
        from src.services.agent.token_monitor import token_monitor

        record = {
            "request_type": endpoint,
            "user_id": user_id,
            "total_usage": {"prompt": prompt, "completion": completion, "total": total, "cached": cached},
            "timestamp": int(time.time() * 1000),
        }
        # fire-and-forget：在已有 event loop 中调度
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(token_monitor.record(record))
        else:
            loop.run_until_complete(token_monitor.record(record))
    except Exception as e:
        logger.warning("token_monitor 记录失败: %s", e)

    # 2. 更新 token_budget_manager（异步 fire-and-forget）
    try:
        from src.services.agent.token_budget import token_budget_manager

        async def _update_budget() -> None:
            if user_id:
                await token_budget_manager.record_user_usage(user_id, total)
            await token_budget_manager.record_global_usage(total)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_update_budget())
        else:
            loop.run_until_complete(_update_budget())
    except Exception as e:
        logger.warning("token_budget 更新失败: %s", e)


# ---------------------------------------------------------------------------
# LangChain AsyncCallbackHandler
# ---------------------------------------------------------------------------


class TokenTrackingCallback(AsyncCallbackHandler):
    """LangChain 回调：在 on_llm_end 中提取并记录 token 用量。

    对齐 Node.js TokenTrackingCallback（BaseCallbackHandler）。
    """

    async def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """LLM 调用结束时提取 token 用量。"""
        llm_output = response.llm_output or {}
        token_usage = llm_output.get("tokenUsage") or llm_output.get("token_usage")
        if not token_usage:
            return

        prompt = int(token_usage.get("promptTokens") or token_usage.get("prompt_tokens") or 0)
        completion = int(token_usage.get("completionTokens") or token_usage.get("completion_tokens") or 0)
        if prompt + completion <= 0:
            return

        cached = int(
            token_usage.get("promptCacheHitTokens")
            or token_usage.get("prompt_cache_hit_tokens")
            or (token_usage.get("promptTokensDetails") or {}).get("cachedTokens", 0)
            or 0
        )

        _record_usage(prompt, completion, cached)


# ---------------------------------------------------------------------------
# 全局单例（对齐 Node.js export const tokenTracker）
# ---------------------------------------------------------------------------

token_tracker = TokenTrackingCallback()


# ---------------------------------------------------------------------------
# 兼容 Node.js recordFetchTokenUsage（非 callback 场景的直接记录）
# ---------------------------------------------------------------------------


def record_fetch_token_usage(data: dict) -> None:
    """记录来自直接 HTTP 调用（非 LangChain）的 token 用量。

    Args:
        data: 包含 usage 字段的响应字典
    """
    usage = (data or {}).get("usage")
    if not usage:
        return
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    cached = int(usage.get("prompt_cache_hit_tokens") or 0)
    if prompt + completion <= 0:
        return
    _record_usage(prompt, completion, cached)
