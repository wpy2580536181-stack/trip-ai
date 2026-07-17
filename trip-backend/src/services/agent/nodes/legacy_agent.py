"""Legacy Agent 节点模块。

使用现有 AgentExecutor 处理一般对话（非规划请求）。
迁移自 Node.js 版本的 legacy_agent 节点（在 chatGraph.ts 中定义）。
"""

import asyncio
import logging
from typing import Any, Optional

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_core.runnables import RunnableConfig

from src.services.agent.types import TokenUsage, StepInput

logger = logging.getLogger(__name__)


async def legacy_agent_node(state: dict, config: RunnableConfig) -> dict:
    """Legacy Agent 节点实现：使用 AgentExecutor 处理一般对话。
    
    这个节点处理非规划请求（route == 'general'），
    使用传统的 AgentExecutor + 工具调用模式。
    
    Args:
        state: 当前状态
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    configurable = config.get("configurable", {})
    on_event = configurable.get("on_event")
    signal = configurable.get("signal")
    build_agent = configurable.get("build_agent")
    conversation_history = configurable.get("conversation_history", [])
    trace_recorder = configurable.get("trace_recorder")
    step_counter = configurable.get("step_counter", {"value": 1})

    # ── Skills 基座：L1 粗选 → L2 规格注入 → L3 指令驱动执行 ──
    # 一般对话路由（route == 'general'）若匹配到技能（如路线优化/酒店搜索），
    # 由技能自行编排底层工具回答；否则降级到下方原有 AgentExecutor 逻辑。
    from src.services.agent.skills import run_selected_skill

    _message = state.get("message", "")
    _llm = configurable.get("llm")
    if _message:
        _skill_result = await run_selected_skill(
            registry=configurable.get("skill_registry"),
            llm=_llm,
            query=_message,
            user_input=_message,
            city=state.get("city"),
            days=state.get("days"),
            budget=state.get("budget"),
            departure_city=state.get("departure_city"),
        )
        if _skill_result is not None and _skill_result.ok:
            logger.info("legacy_agent|skill=%s 命中并执行成功", _skill_result.skill)
            _content = _skill_result.content
            _usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
            if on_event:
                await on_event({"type": "chunk", "content": _content})
            return {"raw_output": _content, "usage": _usage, "skill_used": _skill_result.skill}
        if _skill_result is not None and not _skill_result.ok:
            logger.warning(
                "legacy_agent|skill=%s 执行失败，降级原 agent: %s",
                _skill_result.skill, _skill_result.error,
            )
    # 无人选或技能失败 → 降级到下方原有 AgentExecutor 逻辑

    # 构建输入
    input_dict = {
        "chat_history": [*conversation_history, HumanMessage(content=state.get("message", ""))],
    }
    
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    full_response = ""
    stream_enabled = True
    
    try:
        # 构建 AgentExecutor
        if build_agent:
            executor = await build_agent()
        else:
            # 如果没有提供 build_agent，直接返回简单响应
            return {"raw_output": "抱歉，我暂时无法处理您的请求。", "usage": usage}
        
        # 使用 astream_events 获取流式事件
        event_stream = executor.astream_events(
            input_dict,
            version="v2",
        )
        
        async for event in event_stream:
            if signal and hasattr(signal, "is_set") and signal.is_set():
                break
            
            event_type = event.get("event", "")
            event_name = event.get("name", "unknown")
            
            if event_type == "on_tool_start":
                # 工具调用开始
                stream_enabled = False
                if trace_recorder and step_counter:
                    trace_recorder.add({
                        "step": step_counter["value"],
                        "type": "tool_start",
                        "name": event_name,
                    })
                    step_counter["value"] += 1
                if on_event:
                    await on_event({"type": "tool_start", "name": event_name})
            
            elif event_type == "on_tool_end":
                # 工具调用结束
                full_response = ""  # 重置，不累积工具输出
                stream_enabled = True
                if trace_recorder and step_counter:
                    trace_recorder.add({
                        "step": step_counter["value"],
                        "type": "tool_end",
                        "name": event_name,
                        "duration_ms": None,
                    })
                    step_counter["value"] += 1
                if on_event:
                    await on_event({"type": "tool_end", "name": event_name})
            
            elif event_type == "on_chat_model_stream":
                # LLM 流式输出
                data = event.get("data", {})
                chunk = data.get("chunk")
                
                piece = None
                if chunk:
                    if hasattr(chunk, "content") and isinstance(chunk.content, str):
                        piece = chunk.content
                    elif isinstance(chunk, dict) and "content" in chunk:
                        content = chunk["content"]
                        if isinstance(content, str):
                            piece = content
                        elif isinstance(content, list):
                            # MultiContent
                            piece = "".join(
                                p.get("text", "") if isinstance(p, dict) else str(p)
                                for p in content
                            )
                
                if piece and stream_enabled:
                    full_response += piece
                    if on_event:
                        await on_event({"type": "chunk", "content": piece})
            
            elif event_type == "on_chat_model_end":
                # LLM 输出结束，提取 token 使用量
                data = event.get("data", {})
                output = data.get("output")
                
                if output and hasattr(output, "usage_metadata"):
                    um = output.usage_metadata
                    usage["prompt"] += um.get("input_tokens", 0)
                    usage["completion"] += um.get("output_tokens", 0)
                    usage["total"] += um.get("total_tokens", 0)
                    if um.get("input_token_details"):
                        usage["cached"] += um["input_token_details"].get("cache_read", 0)
        
        return {"raw_output": full_response, "usage": usage}
        
    except Exception as e:
        error_msg = str(e)
        if on_event:
            await on_event({"type": "error", "error": error_msg})
        return {"raw_output": f"处理失败：{error_msg}", "usage": usage}
