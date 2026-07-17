"""Agent 模块。

LangGraph 多智能体编排引擎。
"""

# 导出核心类
from .agent_engine import AgentEngine, get_agent_engine
from src.services.agent.state import PlannerState
from src.services.agent.types import ResearchBundle, TokenUsage, StepInput, PlannerConfig

# 导出图和节点
from .chat_graph import build_chat_graph
from .planner_graph import build_planner_graph
from src.services.agent.nodes import (
    router_node,
    research_node,
    planner_node,
    validate_node,
    chat_planner_node,
    legacy_agent_node,
)

# 导出工具
from src.services.agent.tools import (
    retrieve_knowledge_tool,
    calculate_distance_tool,
    search_hotels_tool,
)

# 导出守卫和监控
from src.services.agent.token_budget import TokenBudgetManager, token_budget_manager
from src.services.agent.semaphore import ConcurrencyGuard, concurrency_guard
from .token_monitor import token_monitor
from src.services.agent.trace_recorder import TraceRecorder

# 导出 Skills 基座（三层渐进式披露，SKILL.md 驱动）
from src.services.agent.skills import (
    Skill,
    SkillRegistry,
    get_skill_registry,
    load_builtin_skills,
    SkillLayer,
    SkillCatalog,
    SkillSpec,
    SkillContext,
    SkillResult,
)

__all__ = [
    # 核心
    "AgentEngine",
    "get_agent_engine",
    "PlannerState",
    "ResearchBundle",
    "TokenUsage",
    "StepInput",
    "PlannerConfig",
    # 图
    "build_chat_graph",
    "build_planner_graph",
    # 节点
    "router_node",
    "research_node",
    "planner_node",
    "validate_node",
    "chat_planner_node",
    "legacy_agent_node",
    # 工具
    "retrieve_knowledge_tool",
    "calculate_distance_tool",
    "search_hotels_tool",
    # 守卫和监控
    "TokenBudgetManager",
    "token_budget_manager",
    "ConcurrencyGuard",
    "concurrency_guard",
    "token_monitor",
    "TraceRecorder",
    # Skills 基座
    "Skill",
    "SkillRegistry",
    "get_skill_registry",
    "load_builtin_skills",
    "SkillLayer",
    "SkillCatalog",
    "SkillSpec",
    "SkillContext",
    "SkillResult",
]
