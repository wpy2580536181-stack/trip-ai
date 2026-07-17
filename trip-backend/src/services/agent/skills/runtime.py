"""节点侧技能运行辅助。

把 AgentEngine 的「技能执行」能力暴露给 LangGraph 节点：节点先由 LLM 基于
L1 目录（route_skill）选出最匹配技能，命中后组装 SkillContext 并交给
registry.execute 走完 L2 规格载入 + L3 指令驱动执行 + L3 资源按需加载。
无人选或执行失败时节点可优雅降级到原有逻辑。
"""

from typing import Any, Optional

from .types import SkillContext


def build_skill_context(
    llm: Any,
    registry: Any,
    user_input: str = "",
) -> SkillContext:
    """为一次技能执行组装 SkillContext（注入 LLM + 三个底层工具 + registry）。

    底层工具供 AgentSkill 在 L3 执行时做 tool calling 自行编排，正是 Skill
    与裸 tool calling 的本质区别。

    Args:
        llm: ChatOpenAI 实例（节点从 config 取得）
        registry: SkillRegistry（L1 目录 / L2 规格 / L3 执行中枢）
        user_input: 用户原始输入，用于拼装执行提示词

    Returns:
        SkillContext
    """
    from src.services.agent.tools import (
        retrieve_knowledge,
        search_hotels,
        calculate_distance,
    )

    return SkillContext(
        llm=llm,
        tools=[retrieve_knowledge, search_hotels, calculate_distance],
        registry=registry,
        user_input=user_input,
    )


async def run_selected_skill(
    registry: Any,
    llm: Any,
    query: str,
    user_input: str = "",
    **kwargs: Any,
) -> Optional["object"]:
    """L1 路由（LLM 选 skill）+ L2/L3 执行的便捷封装。

    节点先用 LLM 基于 L1 目录选出技能（匹配是 LLM 的推理，而非硬编码路由）；
    命中则组装上下文并执行，返回 SkillResult；无人选或执行异常时返回 None
    （调用方据此降级）。

    Args:
        registry: SkillRegistry
        llm: ChatOpenAI 实例
        query: 用于选技能的查询文本（通常是用户消息）
        user_input: 传给技能执行的原始输入
        **kwargs: 技能入参（如 city/days/budget/departure_city）

    Returns:
        SkillResult（命中且执行成功/失败）或 None（无人选）
    """
    if registry is None or llm is None:
        return None

    # L1→L2 路由：优先 LLM 驱动选 skill；失败回退关键字 select
    skill_name = await registry.route_skill(query, llm)
    if not skill_name:
        return None

    ctx = build_skill_context(llm, registry, user_input=user_input)
    return await registry.execute(skill_name, ctx, **kwargs)
