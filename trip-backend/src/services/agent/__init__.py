"""Agent 模块。

LangGraph 多智能体编排引擎。
"""

# 导出核心类
from .agent_engine import AgentEngine, get_agent_engine
from src.services.agent.state import PlannerState
from src.services.agent.types import ResearchBundle, TokenUsage, StepInput, PlannerConfig

# 注：chat_graph.py / planner_graph.py 及 nodes/ 下旧 LangGraph 节点已退出主链路
# （recommend 改由 Orchestrator 纯 asyncio 编排，chat 由 ChatAgent 处理），
# 此处不再导出，避免误以为仍在运行。它们仅被遗留测试引用。

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
