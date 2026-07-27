"""ChatAgent 升级工具定义。

trigger_plan / trigger_modify 是 ChatAgent 的"升级"工具：
当 LLM 判断用户需要全量规划或修改行程时，调用这些工具，
ChatAgent 将请求转交给 Orchestrator 处理。

这些工具本身不执行逻辑，只是作为 LLM 的"意图信号"。
"""

from langchain_core.tools import tool


@tool
def trigger_plan(
    city: str,
    days: int,
    budget: int,
    departure_city: str = "",
    interests: str = "",
) -> str:
    """触发全量行程规划。当用户明确要求生成完整行程时调用此工具。

    Args:
        city: 目的地城市
        days: 游玩天数
        budget: 预算（元）
        departure_city: 出发城市（可选）
        interests: 兴趣偏好描述（可选）
    """
    # 实际逻辑由 ChatAgent 在检测到 tool_call 后交给 Orchestrator
    return f"已触发规划：{city} {days}日游，预算{budget}元"


@tool
def trigger_modify(modify_request: str) -> str:
    """修改已有行程。当用户要求调整/替换/删除行程中的某部分时调用此工具。

    Args:
        modify_request: 修改要求的自然语言描述（如"把第二天的景点换成博物馆"）
    """
    # 实际逻辑由 ChatAgent 在检测到 tool_call 后交给 Orchestrator.modify()
    return f"已触发修改：{modify_request}"
