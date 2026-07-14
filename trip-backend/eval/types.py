"""
Eval 框架类型定义

一个 fixture = 一个测试用例
一个 evaluator = 一个评分函数
Runner 加载所有 fixture，依次跑 evaluator，输出报告
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ToolCall:
    """Agent 工具调用记录（从 agent trace 提取）"""
    name: str
    args: dict = field(default_factory=dict)
    result: Optional[any] = None
    timestamp: Optional[str] = None


@dataclass
class TokenUsage:
    """Token 消耗统计"""
    prompt: int = 0
    completion: int = 0
    total: int = 0
    cached: int = 0


@dataclass
class AgentOutput:
    """Agent 完整输出（runner 收集的产物）"""
    text: str = ""
    json: Optional[dict] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    error: Optional[str] = None
    tokens: Optional[TokenUsage] = None
    duration_ms: int = 0
    conversation_id: Optional[int] = None


@dataclass
class PoiMatch:
    """Fixture expected 中的一种 POI 匹配规则"""
    name: Optional[str] = None           # 精确匹配 POI 名
    name_contains: Optional[str] = None  # 模糊匹配 POI 名（包含即可）
    city: Optional[str] = None           # 期望所在城市
    city_nearby: Optional[str] = None    # 期望所在城市的"附近"范围（基于 100km 半径）


@dataclass
class ToolCallRule:
    """Fixture 中 tool_calls 的一条规则"""
    name: str
    min_calls: int = 0   # 最少调用次数（0 = 不调用）
    max_calls: int = -1  # 最多调用次数（-1 = 无限制）


@dataclass
class FixtureExpected:
    """Fixture expected 节"""
    city: str = ""                                                          # 期望城市（"__SKIP_CITY_CHECK__" = 拒答场景跳过检查）
    spot_names: list[str] = field(default_factory=list)                      # 必含景点名称列表
    must_contain_pois: list[dict] = field(default_factory=list)              # [{name, name_contains, city, city_nearby}]
    must_contain_keywords: list[str] = field(default_factory=list)
    must_not_contain_keywords: list[str] = field(default_factory=list)
    days: int = 0
    json_valid: bool = False
    is_recommendation: bool = False
    is_detail_answer: bool = False
    max_activities_per_day: int = 0
    tool_calls: list[dict] = field(default_factory=list)             # [{name, min_calls, max_calls}]
    activities_have_price_field: bool = False
    contains_price_number: bool = False
    ground_truth: str = ""  # 理想答案（用于 RAGAs Context Recall/Precision）
    keyword_match_mode: str = "all"  # 关键词匹配模式: "all" | "any"


@dataclass
class FixtureInput:
    """Fixture input 节"""
    message: str = ""
    preferences: dict = field(default_factory=dict)
    history: list[dict] = field(default_factory=list)  # [{role: 'user'|'assistant', content: str, timestamp?: str}]


@dataclass
class Fixture:
    """完整 Fixture"""
    id: str
    description: str
    tags: list[str] = field(default_factory=list)
    input: FixtureInput = field(default_factory=FixtureInput)
    expected: FixtureExpected = field(default_factory=FixtureExpected)
    evaluators: list[str] = field(default_factory=list)


@dataclass
class EvalResult:
    """单个 evaluator 跑出来的结果"""
    passed: bool
    reason: str = ""
    details: dict = field(default_factory=dict)


@dataclass
class FixtureResult:
    """Fixture 整体跑出来的结果"""
    fixture_id: str
    description: str
    tags: list[str]
    passed: bool
    agent_output: Optional[AgentOutput] = None
    evaluator_results: dict[str, EvalResult] = field(default_factory=dict)
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class GroupStats:
    """按 tag 或 evaluator 分组的统计"""
    passed: int = 0
    total: int = 0

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0


@dataclass
class ReportSummary:
    """报告总览"""
    total_fixtures: int = 0
    passed_fixtures: int = 0
    failed_fixtures: int = 0
    total_duration_ms: int = 0
    pass_rate: float = 0.0
    by_tag: dict[str, GroupStats] = field(default_factory=dict)
    by_evaluator: dict[str, GroupStats] = field(default_factory=dict)
    total_tokens: Optional[TokenUsage] = None
