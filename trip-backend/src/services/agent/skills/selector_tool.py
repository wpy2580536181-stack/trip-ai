"""select_skill 工具：主 LLM 通过 tool calling 表达"使用某技能"的意图。

对齐 Anthropic 规范：L1 目录常驻主 LLM 上下文，由主 LLM 自行判断何时
激活技能，无需独立路由调用。主 LLM 调用此工具 = 选中技能 → 节点执行技能。
"""

from langchain_core.tools import tool


@tool
def select_skill(skill_name: str) -> str:
    """当你判断用户请求匹配某个可用技能时，调用此工具并传入技能名称。

    仅在用户意图明确匹配 L1 目录中某个技能时才调用；否则不要调用，直接回答。

    Args:
        skill_name: 匹配的技能名称（必须来自可用技能目录）
    """
    return skill_name


def extract_select_skill_call(response) -> str | None:
    """从 LLM 响应中提取 select_skill 工具调用。

    Args:
        response: LLM 的 AIMessage 响应

    Returns:
        技能名称（若 LLM 调用了 select_skill），否则 None
    """
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        return None
    for tc in tool_calls:
        if tc.get("name") == "select_skill":
            return tc.get("args", {}).get("skill_name")
    return None
