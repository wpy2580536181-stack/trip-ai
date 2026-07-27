"""节点侧技能运行辅助。

把 AgentEngine 的「技能执行」能力暴露给 LangGraph 节点：
- 新架构（推荐）：主 LLM 绑定 select_skill 工具，由主 LLM 自行判断是否
  激活技能，无需独立路由调用。节点检测 LLM 响应中的 select_skill 工具调用，
  命中后组装 SkillContext 并交给 registry.execute 走完 L2 规格载入 + L3 指令
  驱动执行 + L3 资源按需加载。
- 旧接口 run_selected_skill 保留向后兼容（内部使用已废弃的 route_skill）。
无人选或执行失败时节点可优雅降级到原有逻辑。
"""

from typing import Any, Optional

from .types import SkillContext, SkillResult
from .selector_tool import select_skill, extract_select_skill_call


def build_skill_context(
    llm: Any,
    registry: Any,
    user_input: str = "",
) -> SkillContext:
    """为一次技能执行组装 SkillContext（注入 LLM + 底层工具 + registry）。

    底层工具供技能在 L3 执行时做 tool calling 自行编排。

    Args:
        llm: ChatOpenAI 实例（节点从 config 取得）
        registry: SkillRegistry（L1 目录 / L2 规格 / L3 执行中枢）
        user_input: 用户原始输入，用于拼装执行提示词

    Returns:
        SkillContext
    """
    from src.services.agent.tools import (
        retrieve_knowledge_tool,
        search_hotels_tool,
        calculate_distance_tool,
        compute_optimal_commute_tool,
        search_commute_tips_tool,
        search_nearby_commute_pois_tool,
    )

    return SkillContext(
        llm=llm,
        tools=[
            retrieve_knowledge_tool,
            search_hotels_tool,
            calculate_distance_tool,
            compute_optimal_commute_tool,
            search_commute_tips_tool,
            search_nearby_commute_pois_tool,
        ],
        registry=registry,
        user_input=user_input,
    )


async def run_skill_if_selected(
    registry: Any,
    llm: Any,
    response: Any,
    user_input: str = "",
    **kwargs: Any,
) -> Optional[SkillResult]:
    """检测主 LLM 响应中的 select_skill 工具调用，命中则执行技能。

    新架构（对齐 Anthropic 规范）：主 LLM 绑定 select_skill 工具 + 域工具，
    单次调用即可同时完成路由 + 规划。LLM 调用 select_skill = 选中技能；
    不调用 = LLM 自行处理（节点使用 LLM 的文本输出）。

    Args:
        registry: SkillRegistry
        llm: ChatOpenAI 实例
        response: 主 LLM 的 AIMessage 响应（可能含 tool_calls）
        user_input: 传给技能执行的原始输入
        **kwargs: 技能入参（如 city/days/budget/departure_city）

    Returns:
        SkillResult（命中且执行）或 None（未选中技能）
    """
    if registry is None or llm is None or response is None:
        return None

    skill_name = extract_select_skill_call(response)
    if not skill_name:
        return None

    # 验证技能是否已注册
    if registry.get(skill_name) is None:
        return None

    ctx = build_skill_context(llm, registry, user_input=user_input)
    return await registry.execute(skill_name, ctx, **kwargs)


async def run_selected_skill(
    registry: Any,
    llm: Any,
    query: str,
    user_input: str = "",
    **kwargs: Any,
) -> Optional[SkillResult]:
    """[DEPRECATED] L1 路由 + L2/L3 执行的便捷封装。

    已废弃：新架构使用 run_skill_if_selected()，由主 LLM 通过 select_skill
    工具自行判断是否激活技能，无需独立路由调用。保留此方法仅为向后兼容。

    Args:
        registry: SkillRegistry
        llm: ChatOpenAI 实例
        query: 用于选技能的查询文本
        user_input: 传给技能执行的原始输入
        **kwargs: 技能入参

    Returns:
        SkillResult 或 None
    """
    if registry is None or llm is None:
        return None

    # 使用已废弃的 route_skill（内部会回退到 select() 关键字匹配）
    skill_name = await registry.route_skill(query, llm)
    if not skill_name:
        return None

    ctx = build_skill_context(llm, registry, user_input=user_input)
    return await registry.execute(skill_name, ctx, **kwargs)
