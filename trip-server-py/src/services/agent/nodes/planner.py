"""Planner 节点模块。

调用 LLM 生成行程规划。
迁移自 Node.js 版本的 nodes/planner.ts。
"""

import asyncio
import json
from typing import Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage

from src.config.settings import settings
from src.services.agent.planner_prompt import build_planner_prompt, build_retry_message
from src.services.agent.types import TokenUsage, StepInput


# 超时配置
RECOMMEND_TIMEOUT_MS = getattr(settings, "AGENT_RECOMMEND_TIMEOUT_MS", 60_000)
RECOMMEND_RETRY_TIMEOUT_MS = getattr(settings, "AGENT_RETRY_TIMEOUT_MS", 30_000)


def _extract_usage_from_result(result: AIMessage) -> TokenUsage:
    """从 LLM 结果中提取 Token 使用情况。
    
    兼容 usage_metadata 和 response_metadata.usage 两种来源。
    
    Args:
        result: AIMessage 结果
        
    Returns:
        Token 使用情况字典
    """
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    
    # 尝试从 usage_metadata 提取
    um = getattr(result, "usage_metadata", None)
    if um:
        usage["prompt"] = um.get("input_tokens", 0)
        usage["completion"] = um.get("output_tokens", 0)
        usage["total"] = um.get("total_tokens", usage["prompt"] + usage["completion"])
        input_details = um.get("input_token_details", {})
        usage["cached"] = input_details.get("cache_read", 0) if isinstance(input_details, dict) else 0
        return usage
    
    # 尝试从 response_metadata.usage 提取
    rm = getattr(result, "response_metadata", None)
    if rm and isinstance(rm, dict):
        ru = rm.get("usage", {})
        if ru and isinstance(ru, dict):
            usage["prompt"] = ru.get("prompt_tokens", 0)
            usage["completion"] = ru.get("completion_tokens", 0)
            usage["total"] = ru.get("total_tokens", usage["prompt"] + usage["completion"])
            prompt_details = ru.get("prompt_tokens_details", {})
            if prompt_details and isinstance(prompt_details, dict):
                usage["cached"] = prompt_details.get("cached_tokens", 0)
            return usage
    
    return usage


async def _invoke_llm(
    llm: Any,
    system_prompt: str,
    user_message: str,
    timeout: float,
) -> tuple[str, TokenUsage]:
    """调用 LLM 并提取结果。
    
    Args:
        llm: ChatOpenAI 实例
        system_prompt: 系统提示词
        user_message: 用户消息
        timeout: 超时时间（秒）
        
    Returns:
        (content, usage) 元组
    """
    # 转义 system_prompt 中的花括号（LangChain 模板语法）
    escaped = system_prompt.replace("{", "{{").replace("}", "}}")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", escaped),
        ("human", "{input}"),
    ])
    
    chain = prompt | llm
    
    try:
        # 使用 asyncio.wait_for 实现超时
        result = await asyncio.wait_for(
            chain.ainvoke({"input": user_message}),
            timeout=timeout / 1000.0,  # 转换为秒
        )
        
        # 提取文本内容
        content = ""
        if isinstance(result, AIMessage):
            content = result.content if isinstance(result.content, str) else ""
            usage = _extract_usage_from_result(result)
        elif isinstance(result, dict):
            content = result.get("content", "")
            usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
        else:
            content = str(result)
            usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
        
        return content, usage
        
    except asyncio.TimeoutError:
        raise TimeoutError(f"planner 执行超时（{timeout / 1000}秒）")


async def planner_node(state: dict, config: dict) -> dict:
    """Planner 节点实现：调用 LLM 生成行程规划。
    
    Args:
        state: 当前状态
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    from ..config.llm import create_llm_from_config, load_fallback_llm_config
    
    configurable = config.get("configurable", {})
    llm = configurable.get("llm")
    fallback_config = configurable.get("fallback_llm_config")
    
    # 构建 planner 提示词
    system_prompt = build_planner_prompt(
        city=state.get("city", ""),
        budget=state.get("budget"),
        days=state.get("days"),
        departure_city=state.get("departure_city"),
        user_preferences=state.get("user_preferences"),
        research_bundle=state.get("research_bundle", {}),
    )
    
    # 构建用户消息
    user_message = state.get("message", "")
    if not user_message:
        city = state.get("city", "")
        days = state.get("days")
        budget = state.get("budget")
        departure = state.get("departure_city", "")
        user_message = f"请为我规划{departure + '出发到' if departure else ''}{city}{days}日游行程，预算{budget}元。"
    
    # 调用 LLM（带主备切换）
    content = ""
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    
    try:
        content, usage = await _invoke_llm(
            llm, system_prompt, user_message,
            RECOMMEND_TIMEOUT_MS,
        )
    except Exception as e:
        # 主 LLM 失败，尝试备用 LLM
        if fallback_config:
            fallback_llm = create_llm_from_config(fallback_config, streaming=False)
            content, usage = await _invoke_llm(
                fallback_llm, system_prompt, user_message,
                RECOMMEND_TIMEOUT_MS,
            )
        else:
            raise e
    
    return {"raw_output": content, "usage": usage}


async def retry_planner_node(state: dict, config: dict) -> dict:
    """重试 Planner 节点：校验失败时重新调用 LLM。
    
    Args:
        state: 当前状态（包含 errors）
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    from ..config.llm import create_llm_from_config, load_fallback_llm_config
    
    configurable = config.get("configurable", {})
    llm = configurable.get("llm")
    fallback_config = configurable.get("fallback_llm_config")
    
    # 构建 planner 提示词
    system_prompt = build_planner_prompt(
        city=state.get("city", ""),
        budget=state.get("budget"),
        days=state.get("days"),
        departure_city=state.get("departure_city"),
        user_preferences=state.get("user_preferences"),
        research_bundle=state.get("research_bundle", {}),
    )
    
    # 构建重试消息（包含错误信息）
    errors = state.get("errors", [])
    error_msg = errors[-1] if errors else "校验失败"
    original_request = state.get("message", "")
    if not original_request:
        city = state.get("city", "")
        days = state.get("days", 0)
        original_request = f"规划{city}{days}日游"
    
    retry_message = build_retry_message(error_msg, original_request)
    
    # 调用 LLM（带主备切换）
    content = ""
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    
    try:
        content, usage = await _invoke_llm(
            llm, system_prompt, retry_message,
            RECOMMEND_RETRY_TIMEOUT_MS,
        )
    except Exception as e:
        if fallback_config:
            fallback_llm = create_llm_from_config(fallback_config, streaming=False)
            content, usage = await _invoke_llm(
                fallback_llm, system_prompt, retry_message,
                RECOMMEND_RETRY_TIMEOUT_MS,
            )
        else:
            raise e
    
    return {"raw_output": content, "usage": usage}
