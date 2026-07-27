"""Agent 间通信 Schema 定义。

定义多 Agent 架构中各组件的输入输出数据结构。
Agent 之间不共享 State，通过这些 Schema 进行明确的契约通信。
"""

from dataclasses import dataclass, field
from typing import Optional, Any


# ---------------------------------------------------------------------------
# 通用数据项
# ---------------------------------------------------------------------------

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

    existing_trip: Optional[dict] = None
    """修改时的已有行程"""

    message: Optional[str] = None
    """用户原始请求"""


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
