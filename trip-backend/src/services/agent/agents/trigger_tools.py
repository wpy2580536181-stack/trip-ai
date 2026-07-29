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
def trigger_patch(
    op: str,
    day: int,
    period: str = "",
    spot_name: str = "",
    description: str = "",
    period_b: str = "",
) -> str:
    """对行程执行精确 Slot 级修改。当用户要求修改单个时段的景点时调用此工具（比 trigger_modify 更快）。

    适合的场景：
    - replace_slot：替换某个时段的景点（如"把第二天下午的故宫换成国博"），需 op=replace_slot, day, period, spot_name
    - remove_slot：清空某个时段（如"删掉第三天上午的安排"），需 op=remove_slot, day, period
    - swap_slot：对调两个时段（如"把第二天上午和下午对调"），需 op=swap_slot, day, period, period_b

    Args:
        op: 操作类型（replace_slot / remove_slot / swap_slot）
        day: 目标天数（从 1 开始）
        period: 目标时段（morning / afternoon / evening）
        spot_name: 新景点名称（replace_slot 必填）
        description: 新景点描述（replace_slot 可选）
        period_b: 第二个时段（swap_slot 必填）
    """
    return f"已触发 patch：{op} day={day} period={period}"


@tool
def trigger_modify(modify_request: str, target_days: str = "") -> str:
    """修改已有行程。当用户要求调整/替换/删除行程中的某部分时调用此工具。

    Args:
        modify_request: 修改要求的自然语言描述（如"把第二天的景点换成博物馆"）
        target_days: 指定要修改的天数（逗号分隔，如"2"表示第2天，"2,3"表示第2、3天）。留空表示全量修改。
    """
    # 实际逻辑由 ChatAgent 在检测到 tool_call 后交给 Orchestrator.modify()
    return f"已触发修改：{modify_request} target_days={target_days}"
