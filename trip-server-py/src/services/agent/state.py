"""LangGraph 状态定义模块。

定义 PlannerState TypedDict，用于 ChatGraph 和 PlannerGraph 的状态管理。
迁移自 Node.js 版本的 state.ts（Annotation.Root → TypedDict）。
"""

from typing import TypedDict, Annotated, Sequence, Optional, Any
from langchain_core.messages import BaseMessage


def add_messages(left: list, right: list) -> list:
    """合并消息列表。
    
    LangGraph Python 使用这个函数来合并消息列表。
    当状态更新时，新的消息会追加到现有消息列表。
    
    Args:
        left: 现有消息列表
        right: 新消息列表
        
    Returns:
        合并后的消息列表
    """
    return left + right


def update_usage(left: dict, right: dict) -> dict:
    """合并 Token 使用情况。
    
    Args:
        left: 现有 Token 使用量
        right: 新增 Token 使用量
        
    Returns:
        合并后的 Token 使用量
    """
    if not left:
        return right
    if not right:
        return left
    
    return {
        "prompt": left.get("prompt", 0) + right.get("prompt", 0),
        "completion": left.get("completion", 0) + right.get("completion", 0),
        "total": left.get("total", 0) + right.get("total", 0),
        "cached": left.get("cached", 0) + right.get("cached", 0),
    }


class PlannerState(TypedDict):
    """PlannerState 状态定义。
    
    这是 ChatGraph 和 PlannerGraph 共享的状态类型。
    对应 Node.js 版本的 Annotation.Root 定义。
    
    字段说明：
        - 输入字段：从用户请求中提取
        - research 产出：research 节点填充
        - planner 产出：planner 节点填充
        - 元数据：用于追踪和调试
    """
    
    # ── 输入字段 ──────────────────────────────────────────────
    
    user_id: int
    """用户 ID"""
    
    message: str
    """用户当前消息"""
    
    city: str
    """目标城市（router 节点会覆盖）"""
    
    budget: Optional[int]
    """预算（元）"""
    
    days: Optional[int]
    """天数"""
    
    departure_city: Optional[str]
    """出发城市"""
    
    user_preferences: Optional[dict]
    """用户偏好设置"""
    
    conversation_history: Annotated[Sequence[BaseMessage], add_messages]
    """对话历史（LangChain 消息格式）"""
    
    # ── research 产出的情报包 ────────────────────────────────
    
    research_bundle: dict
    """research 节点产出的情报包，包含：
        - attractions: 景点信息
        - food: 美食信息
        - hotels: 酒店信息
        - weather: 天气信息
        - distance: 距离信息
    """
    
    # ── planner 产出的原始输出 ──────────────────────────────
    
    raw_output: Optional[str]
    """LLM 原始输出（JSON 字符串）"""
    
    parsed: Optional[dict]
    """解析后的结构化数据（TripContent）"""
    
    # ── 元数据 ─────────────────────────────────────────────────
    
    usage: Annotated[dict, update_usage]
    """Token 使用情况（会自动合并）"""
    
    route: Optional[str]
    """路由结果：'planning' | 'general' | None"""
    
    errors: list[str]
    """错误信息列表"""
