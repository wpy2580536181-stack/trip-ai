"""PlannerGraph 状态图模块。

定义行程规划的状态图（research → planner → validate → retry_planner）。
迁移自 Node.js 版本的 plannerGraph.ts。
"""

from typing import Any

from langgraph.graph import StateGraph, END

from src.services.agent.state import PlannerState
from src.services.agent.nodes import research_node, planner_node, validate_node, retry_planner_node


def build_planner_graph():
    """构建 PlannerGraph 状态图。
    
    流程图：
        __start__ → research
        research → planner
        planner → validate
        validate → retry_planner (if parsed is None)
        validate → END (if parsed is not None)
        retry_planner → END
    
    Returns:
        编译后的状态图
    """
    graph = StateGraph(PlannerState)
    
    # ── 添加节点 ──────────────────────────────────────────────────
    
    # research 节点：并行调用工具获取情报
    graph.add_node("research", research_node)
    
    # planner 节点：调用 LLM 生成行程规划
    graph.add_node("planner", planner_node)
    
    # validate 节点：校验 LLM 输出的 JSON
    graph.add_node("validate", validate_node)
    
    # retry_planner 节点：校验失败时重试
    graph.add_node("retry_planner", retry_planner_node)
    
    # ── 添加边 ──────────────────────────────────────────────────
    
    # 入口：__start__ → research
    graph.set_entry_point("research")
    graph.add_edge("__start__", "research")
    
    # research → planner
    graph.add_edge("research", "planner")
    
    # planner → validate
    graph.add_edge("planner", "validate")
    
    # 条件边：validate → retry_planner 或 END
    graph.add_conditional_edges(
        "validate",
        _validate_decision,
        {
            "end": END,
            "retry": "retry_planner",
        },
    )
    
    # retry_planner → END（避免无限循环）
    graph.add_edge("retry_planner", END)
    
    return graph.compile()


def _validate_decision(state: dict) -> str:
    """条件边决策函数（validate 节点后）。
    
    Args:
        state: 当前状态
        
    Returns:
        "end" 如果解析成功，"retry" 如果解析失败
    """
    parsed = state.get("parsed")
    if parsed is not None:
        return "end"
    return "retry"
