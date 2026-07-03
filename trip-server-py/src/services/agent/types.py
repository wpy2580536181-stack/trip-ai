"""Agent 类型定义模块。

定义 ResearchBundle、PlannerConfig 等类型。
迁移自 Node.js 版本的 types.ts。
"""

from typing import Any, Optional, Callable, Awaitable
from typing_extensions import TypedDict


class ResearchBundle(TypedDict, total=False):
    """research 节点产出的情报包。
    
    对应 Node.js 版本的 ResearchBundle 接口。
    所有字段都是可选的，因为某些工具调用可能失败。
    """
    
    attractions: Optional[str]
    """景点信息（来自 retrieve_knowledge 工具）"""
    
    food: Optional[str]
    """美食信息（来自 retrieve_knowledge 工具）"""
    
    hotels: Optional[str]
    """酒店信息（来自 search_hotels 工具）"""
    
    weather: Optional[str]
    """天气信息（来自 maps_weather 工具）"""
    
    distance: Optional[str]
    """距离信息（来自 calculate_distance 工具）"""


class TokenUsage(TypedDict):
    """Token 使用情况。"""
    
    prompt: int
    """输入 Token 数"""
    
    completion: int
    """输出 Token 数"""
    
    total: int
    """总 Token 数"""
    
    cached: int
    """缓存命中 Token 数"""


class StepInput(TypedDict, total=False):
    """Trace 步骤输入。
    
    对应 Node.js 版本的 StepInput 接口。
    """
    
    step: int
    """步骤编号"""
    
    type: str
    """步骤类型：'tool_start' | 'tool_end' | 'chunk' | 'complete' | 'error' | 'thinking'"""
    
    name: Optional[str]
    """工具或节点名称"""
    
    args: Optional[dict]
    """工具调用参数"""
    
    output: Optional[str]
    """输出内容"""
    
    duration_ms: Optional[int]
    """耗时（毫秒）"""
    
    error: Optional[str]
    """错误信息"""
    
    parent_step_id: Optional[int]
    """父步骤 ID"""
    
    thinking_content: Optional[str]
    """思考内容"""


class PlannerConfig(TypedDict, total=False):
    """LangGraph config.configurable 注入的非可变依赖。
    
    对应 Node.js 版本的 PlannerConfig 接口。
    这些配置会在 graph.invoke() 时通过 config 参数传入。
    """
    
    trace_recorder: Any
    """TraceRecorder 实例"""
    
    on_event: Callable[[dict], Awaitable[None]]
    """事件回调函数"""
    
    signal: Optional[Any]
    """asyncio.Event 用于中止信号"""
    
    step_counter: dict
    """步骤计数器（可变对象，跨节点共享）"""
    
    llm: Any
    """ChatOpenAI 实例"""
    
    fallback_llm_config: Optional[dict]
    """备用 LLM 配置"""
    
    system_prompt: Optional[str]
    """系统提示词（用于 legacy_agent 节点）"""
    
    build_agent: Optional[Callable]
    """延迟构建 AgentExecutor 的工厂函数"""
    
    conversation_history: Optional[list]
    """对话历史（用于 legacy_agent 节点）"""


def empty_usage() -> TokenUsage:
    """创建空的 TokenUsage。
    
    Returns:
        空的 TokenUsage 字典
    """
    return {
        "prompt": 0,
        "completion": 0,
        "total": 0,
        "cached": 0,
    }
