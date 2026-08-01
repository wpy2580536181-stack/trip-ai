"""预算修正器：超支行程 + 预算分解目标 → CorrectorAction（纯函数，无 LLM/IO/状态）。"""

from src.services.agent.schemas import BudgetAllocation, CorrectorAction

_ITEM_NAMES = {
    "accommodation": "住宿",
    "food": "餐饮",
    "transportation": "交通",
    "tickets": "门票",
    "other": "其他",
}

_ROUND_ACTIONS = {
    1: {"tickets": 0.6, "food": 0.9},
    2: {"accommodation": 0.7},
    3: {"transportation": 0.8, "other": 0},
}

_ROUND_TIPS = {
    1: "优先替换为免费景点，收紧餐饮消费",
    2: "降低酒店档次，选择更经济的住宿",
    3: "减少付费活动，控制交通成本",
}


def _round10(value: int) -> int:
    """金额取整到 10 元。"""
    return int(round(value / 10) * 10)


def build_correction(plan: dict, alloc: BudgetAllocation, round: int) -> CorrectorAction:
    """输出本轮目标分解 + 结构化指令。绝不修改入参 plan。"""
    if not isinstance(round, int) or round < 1:
        round = 1
    if round > 3:
        round = 3

    over_amount = plan["totalBudget"] - alloc.budget

    targets = {key: _round10(value) for key, value in alloc.allocation.items()}
    for key, factor in _ROUND_ACTIONS[round].items():
        if key in targets:
            targets[key] = _round10(int(targets[key] * factor))

    tips = _ROUND_TIPS[round]
    parts = [f"当前第 {round} 轮预算修正：超支 {over_amount} 元。"]
    parts.append("目标分解：" + "、".join(
        f"{_ITEM_NAMES.get(key, key)}目标 ≤ {value} 元" for key, value in targets.items()
    ))
    parts.append(f"请按目标重新组合行程，替换指引：{tips}。")
    instructions = "\n".join(parts)

    return CorrectorAction(
        round=round,
        over_amount=over_amount,
        target_allocation=targets,
        instructions=instructions,
    )
