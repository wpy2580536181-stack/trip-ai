"""Agent 间通信 Schema 定义。

定义多 Agent 架构中各组件的输入输出数据结构。
Agent 之间不共享 State，通过这些 Schema 进行明确的契约通信。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any


# ---------------------------------------------------------------------------
# 通用数据项
# ---------------------------------------------------------------------------

class CostSource(str, Enum):
    """行程费用来源标记。

    - RAG: spots.avg_cost 真实值（knowledge_service 检索返回）
    - MEITUAN: 美团查得真实价（预留枚举，生成链路当前只读不主动查询）
    - ESTIMATE: cost_estimator 按城市消费档位估算
    - DISTANCE: calculate_distance 交通费用粗算（既有能力）
    """

    RAG = "rag"
    MEITUAN = "meituan"
    ESTIMATE = "estimate"
    DISTANCE = "distance"


@dataclass
class SpotItem:
    """景点/餐厅等 POI 数据项。"""

    name: str
    """名称"""

    source_id: Optional[str] = None
    """来源 ID（来自 ChromaDB 或 MCP，用于候选池合规校验）"""

    category: Optional[str] = None
    """分类：attraction / food / hotel"""

    rating: Optional[float] = None
    """评分"""

    address: Optional[str] = None
    """地址"""

    cost: Optional[str] = None
    """费用描述"""

    raw: Optional[str] = None
    """原始文本（兼容当前 RAG 返回的纯文本格式）"""

    avg_cost: Optional[float] = None
    """人均消费（真实值，来自 spots.avg_cost；无值时为 None）"""

    cost_source: Optional[CostSource] = None
    """费用来源标记（见 CostSource 枚举）"""


# ---------------------------------------------------------------------------
# Orchestrator 入口
# ---------------------------------------------------------------------------

@dataclass
class PlanRequest:
    """规划请求（Orchestrator.plan 的输入）。"""

    user_id: int
    city: str
    days: int
    budget: int
    departure_city: Optional[str] = None
    preferences: Optional[dict] = None
    message: Optional[str] = None
    """用户原始消息（可选，用于日志和 trace）"""


@dataclass
class PlanResult:
    """规划结果（Orchestrator.plan 的输出）。"""

    plan: Optional[dict] = None
    """结构化行程 JSON（dailyItinerary + budgetBreakdown + tips）"""

    raw_output: Optional[str] = None
    """LLM 原始输出文本"""

    review: Optional["ReviewResult"] = None
    """审阅结果"""

    usage: dict = field(default_factory=lambda: {
        "prompt": 0, "completion": 0, "total": 0, "cached": 0,
    })
    """总 Token 消耗（所有 Agent 汇总）"""

    duration_ms: int = 0
    """总耗时"""

    error: Optional[str] = None
    """错误信息"""


# ---------------------------------------------------------------------------
# ResearchAgent
# ---------------------------------------------------------------------------

@dataclass
class ResearchInput:
    """ResearchAgent 输入。"""

    city: str
    days: int
    budget: Optional[int] = None
    interests: list[str] = field(default_factory=list)
    """用户兴趣标签"""

    departure_city: Optional[str] = None
    constraints: Optional[str] = None
    """自然语言约束（如"不要爬山"、"带老人"）"""

    exclude_spots: list[str] = field(default_factory=list)
    """修改行程时排除已有景点"""

    user_preferences: Optional[dict] = None
    """用户偏好字典（兼容现有格式）"""


@dataclass
class ResearchBundle:
    """ResearchAgent 输出（候选池）。

    兼容当前 research_node 的纯文本格式（raw 字段），
    同时支持结构化的 SpotItem 列表（后续升级）。
    """

    attractions: Optional[str] = None
    """景点信息（RAG 返回的文本）"""

    food: Optional[str] = None
    """美食信息"""

    hotels: Optional[str] = None
    """酒店信息"""

    weather: Optional[str] = None
    """天气信息"""

    distance: Optional[str] = None
    """距离/交通信息"""

    # 结构化候选池（后续升级用）
    attraction_items: list[SpotItem] = field(default_factory=list)
    food_items: list[SpotItem] = field(default_factory=list)
    hotel_items: list[SpotItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        """转为 dict（兼容现有 planner_prompt._format_bundle）。"""
        return {
            "attractions": self.attractions,
            "food": self.food,
            "hotels": self.hotels,
            "weather": self.weather,
            "distance": self.distance,
        }

    def all_spot_names(self) -> set[str]:
        """获取候选池中所有景点名称（用于封闭世界校验）。"""
        names = set()
        for item in self.attraction_items:
            names.add(item.name)
        for item in self.food_items:
            names.add(item.name)
        return names


# ---------------------------------------------------------------------------
# PlannerAgent
# ---------------------------------------------------------------------------

@dataclass
class PlannerInput:
    """PlannerAgent 输入。"""

    bundle: ResearchBundle
    """候选池（ResearchAgent 的输出）"""

    city: str
    days: int
    budget: int
    preferences: Optional[dict] = None
    departure_city: Optional[str] = None

    feedback: Optional[str] = None
    """review 修改意见（重试时注入）"""

    budget_correction: Optional["CorrectorAction"] = None
    """预算修正指令（corrector 输出，重试时结构化注入；prompt 渲染为修正段落）"""

    existing_trip: Optional[dict] = None
    """修改时的已有行程"""

    target_days: Optional[list[int]] = None
    """局部修改时指定只重新生成哪些天（如 [2] 表示只改第 2 天）"""

    message: Optional[str] = None
    """用户原始请求"""

    variant_type: Optional[str] = None
    """多路线对比时的 variant 类型：economy / comfort / photo"""


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

@dataclass
class ReviewResult:
    """审阅结果。"""

    passed: bool
    """是否通过"""

    issues: list[str] = field(default_factory=list)
    """发现的问题列表"""

    feedback: str = ""
    """注入 Planner 的修改指令（不通过时有值）"""

    code_checks: dict = field(default_factory=dict)
    """代码层校验明细"""


# ---------------------------------------------------------------------------
# Multi-Variant Planning（P0：2-3 条路线对比）
# ---------------------------------------------------------------------------

@dataclass
class VariantResult:
    """单个 variant 的规划结果。"""

    variant_type: str = ""
    """variant 类型：economy / comfort / photo"""

    label: str = ""
    """展示标签：💰 经济型 / ⭐ 舒适型 / 📸 打卡型"""

    plan: Optional[dict] = None
    """结构化行程 JSON（dailyItinerary + budgetBreakdown + tips）"""

    raw_output: Optional[str] = None
    """LLM 原始输出文本"""

    review: Optional["ReviewResult"] = None
    """审阅结果"""

    usage: dict = field(default_factory=lambda: {
        "prompt": 0, "completion": 0, "total": 0, "cached": 0,
    })
    """Token 消耗"""

    duration_ms: int = 0
    """耗时（毫秒）"""

    error: Optional[str] = None
    """错误信息（失败时非空）"""


@dataclass
class PlanVariantsResult:
    """多 variant 规划结果（Orchestrator.plan_variants 的输出）。"""

    variants: list[VariantResult] = field(default_factory=list)
    """variant 列表（长度通常为 3）"""

    research_usage: dict = field(default_factory=lambda: {
        "prompt": 0, "completion": 0, "total": 0, "cached": 0,
    })
    """Research 阶段共享的 Token 消耗"""

    total_duration_ms: int = 0
    """总耗时（毫秒）"""

    error: Optional[str] = None
    """整体错误信息（如 Research 阶段失败时非空，此时 variants 为空）"""


# ---------------------------------------------------------------------------
# 预算控制引擎（Budget Allocator / Corrector）
# ---------------------------------------------------------------------------

@dataclass
class BudgetAllocation:
    """预算分解目标（allocator 输出，纯确定性）。

    5 项上限金额为"生成时基准"，校验时按 elasticity 放行。
    """

    budget: int
    """用户预算（元）"""

    days: int
    """行程天数"""

    style: str
    """旅行风格：budget / comfort / luxury"""

    allocation: dict[str, int] = field(default_factory=dict)
    """5 项上限：accommodation / food / transportation / tickets / other → 金额"""

    daily_activity_limit: int = 0
    """每日活动费用上限（元）"""

    elasticity: float = 1.15
    """单项弹性系数：单项 ≤ 上限×elasticity 放行"""


@dataclass
class CorrectorAction:
    """预算修正动作（corrector 输出，纯确定性）。

    只输出"目标分配 + 指令"，不回写任何金额（区别于竞品直接打折）。
    PlannerAgent 在真实数据上按目标重新组合。
    """

    round: int
    """修正轮次：1=砍门票/收紧餐饮，2=降住宿档，3=砍交通/清零其他"""

    over_amount: int
    """超支金额（元）"""

    target_allocation: dict[str, int]
    """本轮目标分解（5 项上限，已按轮次降级）"""

    instructions: str
    """结构化中文指令（给 PlannerAgent）"""

    keep_scope: str = "full"
    """重生成范围：full（本期恒为 full）；budget_only 为 P1 局部重生成预留"""


@dataclass
class BudgetViolation:
    """单项预算违规明细。"""

    key: str
    """违规分项：tickets / accommodation / food / ..."""

    actual: int
    """实际金额（元）"""

    limit: int
    """分项上限（元）"""

    over: int
    """超出金额（元）"""


@dataclass
class BudgetViolationResult:
    """预算分项校验结果（review 代码层输出）。"""

    violations: list[BudgetViolation] = field(default_factory=list)
    """违规明细列表（为空表示无违规）"""

    over_amount: int = 0
    """违规总超出金额（元）"""

    feedback: str = ""
    """结构化打回反馈（含分项明细 + 目标分配）"""

    @property
    def passed(self) -> bool:
        return not self.violations
