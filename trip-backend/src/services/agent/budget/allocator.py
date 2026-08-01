"""预算分解器：budget/days/style → BudgetAllocation（纯函数，无 LLM/IO/状态）。"""

from src.services.agent.schemas import BudgetAllocation

_RATIOS = {
    "comfort": {
        "accommodation": 0.40,
        "food": 0.25,
        "transportation": 0.20,
        "tickets": 0.10,
        "other": 0.05,
    },
    "budget": {
        "accommodation": 0.35,
        "food": 0.30,
        "transportation": 0.15,
        "tickets": 0.15,
        "other": 0.05,
    },
    "luxury": {
        "accommodation": 0.50,
        "food": 0.20,
        "transportation": 0.15,
        "tickets": 0.10,
        "other": 0.05,
    },
}


def round_to_10(amount: float) -> int:
    """金额取整到 10 元。"""
    return int(round(amount / 10) * 10)


def allocate(budget: int, days: int, style: str = "comfort", elasticity: float = 1.15) -> BudgetAllocation:
    """按风格占比分解预算为 5 项上限金额。

    未知 style 回退 comfort；budget ≤ 2000 时低档兜底：
    food 上浮 5%、tickets 提升到 15%，差额从 accommodation 扣减以保持总和 100%。
    """
    ratios = dict(_RATIOS.get(style, _RATIOS["comfort"]))
    if budget <= 2000:
        bump = 0.05 + max(0.15 - ratios["tickets"], 0.0)
        ratios["food"] += 0.05
        ratios["tickets"] = max(ratios["tickets"], 0.15)
        ratios["accommodation"] -= bump
    allocation = {key: round_to_10(budget * ratio) for key, ratio in ratios.items()}
    daily_activity_limit = round_to_10(budget / days * 0.30)
    return BudgetAllocation(
        budget=budget,
        days=days,
        style=style,
        allocation=allocation,
        daily_activity_limit=daily_activity_limit,
        elasticity=elasticity,
    )
