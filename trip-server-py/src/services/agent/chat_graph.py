"""ChatGraph 状态图模块。

定义多轮对话的状态图（router -> research/legacy_agent -> chat_planner）。
迁移自 Node.js 版本的 chatGraph.ts。
"""

import re
from typing import Any, Optional

from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage

from src.services.agent.state import PlannerState
from src.services.agent.nodes import router_node, research_node, chat_planner_node, legacy_agent_node


# 常见旅游城市列表（用于提取城市关键词）
CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "重庆", "南京",
    "天津", "长沙", "苏州", "厦门", "青岛", "大连", "昆明", "三亚", "哈尔滨", "桂林",
    "拉萨", "乌鲁木齐", "贵阳", "南宁", "南昌", "福州", "合肥", "郑州", "济南", "太原", "兰州",
    # 常见旅游目的地
    "丽江", "大理", "西双版纳", "张家界", "九寨沟", "黄山", "鼓浪屿", "凤凰", "平遥", "敦煌",
    "婺源", "稻城", "林芝", "纳木错", "喀纳斯", "伊犁", "阿尔山", "雪乡", "漠河", "北海",
    "涠洲岛", "舟山", "普陀山", "嵊泗", "千岛湖", "乌镇", "西塘", "周庄", "香格里拉",
    # 国际城市（常见旅行目的地）
    "东京", "大阪", "京都", "奈良", "首尔", "曼谷", "新加坡", "吉隆坡", "巴厘岛", "普吉岛",
    "巴黎", "伦敦", "纽约", "洛杉矶", "悉尼", "墨尔本", "莫斯科", "迪拜", "多哈", "伊斯坦布尔",
]


def _extract_city_from_message(message: str) -> Optional[str]:
    """从消息文本中提取城市关键词。
    
    Args:
        message: 用户消息
        
    Returns:
        匹配的城市名，未命中则返回 None
    """
    for city in CITIES:
        if city in message:
            return city
    return None


def _extract_city_from_history(history: list) -> Optional[str]:
    """从对话历史中提取城市关键词（多轮修改场景 message 可能不包含城市名）。
    
    Args:
        history: 对话历史消息列表
        
    Returns:
        匹配的城市名，未命中则返回 None
    """
    for msg in history:
        # 处理 LangChain 消息对象
        content = ""
        if hasattr(msg, "content"):
            content = msg.content if isinstance(msg.content, str) else ""
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        
        for city in CITIES:
            if city in content:
                return city
    return None


def build_chat_graph():
    """构建 ChatGraph 状态图。
    
    流程图：
        __start__ -> router
        router -> research (if route == 'planning')
        router -> legacy_agent (if route == 'general')
        research -> chat_planner
        chat_planner -> END
        legacy_agent -> END
    
    Returns:
        编译后的状态图
    """
    graph = StateGraph(PlannerState)
    
    # 添加节点
    # router 节点：判断是规划请求还是一般对话
    graph.add_node("router", _router_node_wrapper)
    
    # research 节点：并行调用工具获取情报
    graph.add_node("research", research_node)
    
    # chat_planner 节点：基于 research 结果生成回答
    graph.add_node("chat_planner", chat_planner_node)
    
    # legacy_agent 节点：使用 AgentExecutor 处理一般对话
    graph.add_node("legacy_agent", legacy_agent_node)
    
    # 添加边
    # 入口：__start__ -> router
    graph.set_entry_point("router")
    
    # 条件边：router -> research 或 legacy_agent
    # _route_decision 直接返回目标节点名称
    graph.add_conditional_edges(
        "router",
        _route_decision,
    )
    
    # research -> chat_planner
    graph.add_edge("research", "chat_planner")
    
    # chat_planner -> END
    graph.add_edge("chat_planner", END)
    
    # legacy_agent -> END
    graph.add_edge("legacy_agent", END)
    
    return graph.compile()


def _router_node_wrapper(state: dict) -> dict:
    """router 节点包装函数（避免循环导入）。
    
    Args:
        state: 当前状态
        
    Returns:
        更新的状态字段
    """
    # router_node 已包含完整的 route + city 判断逻辑
    return router_node(state)


def _route_decision(state: dict) -> str:
    """条件边决策函数。
    
    Args:
        state: 当前状态
        
    Returns:
        下一个节点名称
    """
    route = state.get("route", "general")
    if route == "planning":
        return "research"
    return "legacy_agent"
