"""ChatPlanner 节点模块。

基于 research 结果生成流式回答。
迁移自 Node.js 版本的 nodes/chatPlanner.ts。
"""

import asyncio
from typing import Any, Optional

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

from src.services.agent.planner_prompt import build_chat_planner_static_prompt
from src.services.agent.types import TokenUsage, StepInput


# 工具名称映射（research bundle key -> tool name）
TOOL_NAMES = {
    "attractions": "retrieve_knowledge",
    "food": "retrieve_knowledge",
    "hotels": "search_hotels",
    "distance": "calculate_distance",
    "weather": "maps_weather",
}


def _build_tool_call_messages(bundle: dict) -> list:
    """把 research 的 bundle 转成标准 tool call 协议消息。
    
    模拟 LLM 真实调工具的消息格式：
    - 一条 AIMessage 携带多个 tool_calls
    - 每条工具结果对应一条 ToolMessage
    
    Args:
        bundle: ResearchBundle 字典
        
    Returns:
        消息列表 [ToolCallAIMsg, ToolMsg1, ToolMsg2, ...]
    """
    import time
    
    entries = [(k, v) for k, v in bundle.items() if v and isinstance(v, str)]
    if not entries:
        return []
    
    call_id_base = f"call_research_{int(time.time() * 1000)}_"
    
    # 构建 tool_calls 列表
    tool_calls = []
    for i, (key, _) in enumerate(entries):
        tool_calls.append({
            "id": f"{call_id_base}{i}_{key}",
            "name": TOOL_NAMES.get(key, "retrieve_knowledge"),
            "args": {},
        })
    
    # 一条 AIMessage 携带多个 tool_calls
    tool_call_msg = AIMessage(
        content="",
        tool_calls=tool_calls,
    )
    
    # 每条工具结果对应一条 ToolMessage
    tool_msgs = []
    for i, (key, value) in enumerate(entries):
        tool_msgs.append(
            ToolMessage(
                content=value,
                tool_call_id=f"{call_id_base}{i}_{key}",
                name=TOOL_NAMES.get(key, "retrieve_knowledge"),
            )
        )
    
    return [tool_call_msg] + tool_msgs


def _extract_token_text(event: dict) -> Optional[str]:
    """从 stream event 中提取文本片段。
    
    Args:
        event: LangChain stream event
        
    Returns:
        文本片段，如果无法提取则返回 None
    """
    data = event.get("data")
    if not data or not isinstance(data, dict):
        return None
    
    chunk = data.get("chunk")
    if not chunk:
        return None
    
    content = chunk.content if hasattr(chunk, "content") else None
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        # 处理 MultiContent (list of content parts)
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    
    return None


def _extract_usage(event: dict, usage: TokenUsage) -> None:
    """从 stream event 中提取 Token 使用量并更新。
    
    Args:
        event: LangChain stream event
        usage: TokenUsage 字典（会被原地更新）
    """
    data = event.get("data", {})
    output = data.get("output")
    
    if not output:
        return
    
    # 尝试获取 kwargs
    kwargs = None
    if hasattr(output, "to_json"):
        try:
            json_obj = output.to_json()
            kwargs = json_obj.get("kwargs", {})
        except Exception:
            pass
    
    if not kwargs and isinstance(output, dict):
        kwargs = output.get("kwargs", {})
    
    if not kwargs:
        return
    
    # 从 usage_metadata 提取
    um = kwargs.get("usage_metadata", {})
    if um and isinstance(um, dict):
        usage["prompt"] = usage.get("prompt", 0) + um.get("input_tokens", 0)
        usage["completion"] = usage.get("completion", 0) + um.get("output_tokens", 0)
        usage["total"] = usage.get("total", 0) + um.get("total_tokens", 0)
        input_details = um.get("input_token_details", {})
        if isinstance(input_details, dict):
            usage["cached"] = usage.get("cached", 0) + input_details.get("cache_read", 0)
        return
    
    # 从 response_metadata.usage 提取
    rm = kwargs.get("response_metadata", {})
    if rm and isinstance(rm, dict):
        ru = rm.get("usage", {})
        if ru and isinstance(ru, dict):
            usage["prompt"] = usage.get("prompt", 0) + ru.get("prompt_tokens", 0)
            usage["completion"] = usage.get("completion", 0) + ru.get("completion_tokens", 0)
            usage["total"] = usage.get("total", 0) + ru.get("total_tokens", 0)
            prompt_details = ru.get("prompt_tokens_details", {})
            if isinstance(prompt_details, dict):
                usage["cached"] = usage.get("cached", 0) + prompt_details.get("cached_tokens", 0)


async def chat_planner_node(state: dict, config: dict) -> dict:
    """ChatPlanner 节点实现：基于 research 结果生成流式回答。
    
    Args:
        state: 当前状态
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    configurable = config.get("configurable", {})
    on_event = configurable.get("on_event")
    signal = configurable.get("signal")
    llm = configurable.get("llm")
    fallback_llm_config = configurable.get("fallback_llm_config")
    
    # system prompt 纯静态（不依赖 RAG/用户输入）
    system_prompt = build_chat_planner_static_prompt()
    escaped = system_prompt.replace("{", "{{").replace("}", "}}")
    
    # research bundle -> 标准 tool call 协议消息
    research_bundle = state.get("research_bundle", {})
    tool_messages = _build_tool_call_messages(research_bundle)
    
    # 构建完整消息列表
    full_messages = [SystemMessage(content=escaped)]
    
    # 添加对话历史
    conversation_history = state.get("conversation_history", [])
    if conversation_history:
        full_messages.extend(conversation_history)
    
    # 添加 tool messages（模拟工具调用结果）
    if tool_messages:
        full_messages.extend(tool_messages)
    
    # 添加当前用户消息
    user_message = state.get("message", "")
    full_messages.append(HumanMessage(content=user_message))
    
    # 初始化
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    full_response = ""
    
    async def run_stream(current_llm):
        """运行流式 LLM 调用。"""
        nonlocal full_response, usage
        
        # 使用 astream_events 获取流式事件
        event_stream = current_llm.astream_events(
            input=full_messages,
            version="v2",
            signal=signal,
        )
        
        async for event in event_stream:
            if signal and hasattr(signal, "is_set") and signal.is_set():
                break
            
            event_type = event.get("event", "")
            
            if event_type == "on_chat_model_stream":
                # 处理流式输出
                piece = _extract_token_text(event)
                if piece:
                    full_response += piece
                    if on_event:
                        await on_event({"type": "chunk", "content": piece})
            
            elif event_type == "on_chat_model_end":
                # 提取最终 token 使用量
                _extract_usage(event, usage)
    
    try:
        await run_stream(llm)
    except Exception as e:
        # 主 LLM 失败，尝试备用 LLM
        if fallback_llm_config:
            from ..config.llm import create_llm_from_config
            fallback_llm = create_llm_from_config(fallback_llm_config, streaming=True)
            await run_stream(fallback_llm)
        else:
            raise e
    
    return {"raw_output": full_response, "usage": usage}
