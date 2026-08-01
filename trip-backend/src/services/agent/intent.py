"""Intent 意图抽取模块（函数，非 Agent）。

两级设计：
- fast-path：关键词/正则命中 → 直接返回结构化参数（省 LLM 调用）
- slow-path：fallback 小模型做一次结构化抽取（Phase 5 启用）

取代当前 nodes/router.py + chat_graph.py 中的 CITIES 列表。
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 城市列表（从 chat_graph.py 移植）
# ---------------------------------------------------------------------------

CITIES = [
    "北京", "上海", "广州", "深圳", "成都", "杭州", "武汉", "西安", "重庆", "南京",
    "天津", "长沙", "苏州", "厦门", "青岛", "大连", "昆明", "三亚", "哈尔滨", "桂林",
    "拉萨", "乌鲁木齐", "贵阳", "南宁", "南昌", "福州", "合肥", "郑州", "济南", "太原", "兰州",
    "丽江", "大理", "西双版纳", "张家界", "九寨沟", "黄山", "鼓浪屿", "凤凰", "平遥", "敦煌",
    "婺源", "稻城", "林芝", "纳木错", "喀纳斯", "伊犁", "阿尔山", "雪乡", "漠河", "北海",
    "涠洲岛", "舟山", "普陀山", "嵊泗", "千岛湖", "乌镇", "西塘", "周庄", "香格里拉",
    "东京", "大阪", "京都", "奈良", "首尔", "曼谷", "新加坡", "吉隆坡", "巴厘岛", "普吉岛",
    "巴黎", "伦敦", "纽约", "洛杉矶", "悉尼", "墨尔本", "莫斯科", "迪拜", "多哈", "伊斯坦布尔",
]

# 规划请求关键词（从 router.py 移植）
PLANNING_KEYWORDS = [
    "规划", "行程", "几日游", "攻略", "安排", "路线", "帮我计划", "怎么玩",
    "旅游", "旅行", "出游", "度假", "自由行", "自驾游", "跟团",
    "必去", "景点", "美食", "住宿", "酒店",
    "推荐", "建议", "调整", "方案", "计划", "打算", "想去", "出发", "去哪",
    "玩", "去", "逛", "打卡", "体验", "看看", "走走", "路过",
    "预算", "花钱", "省钱", "穷游", "花费", "多少钱",
    "码头", "船票", "门票", "出发时间", "怎么去", "多远",
]

DAYS_PATTERN = re.compile(r"([\d一二三四五六七八九十两]+)\s*(?:日|天)")
BUDGET_PATTERN = re.compile(r"(\d+)\s*(?:元|块|圆)")


# ---------------------------------------------------------------------------
# 输出 Schema
# ---------------------------------------------------------------------------

@dataclass
class IntentResult:
    """意图抽取结果。"""

    route: str = "general"
    """路由：'planning' | 'general' | 'clarify'"""

    city: Optional[str] = None
    days: Optional[int] = None
    budget: Optional[int] = None
    departure_city: Optional[str] = None
    interests: list[str] = field(default_factory=list)

    clarify_question: Optional[str] = None
    """route == 'clarify' 时的追问内容"""


@dataclass
class ClarifyField:
    """追问字段定义（用于前端渲染表单）。"""

    key: str
    """字段名：city / days / budget / departure_city"""

    label: str
    """前端标签：目的地 / 天数 / 预算 / 出发城市"""

    field_type: str
    """输入类型：select | text | number"""

    required: bool = True
    """是否必填"""

    placeholder: str = ""
    """占位提示"""

    options: list[str] = field(default_factory=list)
    """select 类型时的选项列表"""


@dataclass
class ClarifyCardData:
    """ClarifyCard 前端数据结构。"""

    fields: list[ClarifyField]
    title: str = "请补充以下信息"
    submit_label: str = "开始规划"
    cancel_label: str = "取消"


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------

def extract_intent(message: str, history: Optional[list] = None) -> IntentResult:
    """Fast-path 意图抽取（纯规则，不调 LLM）。

    Args:
        message: 用户消息
        history: 对话历史（LangChain 消息列表）

    Returns:
        IntentResult 结构化意图
    """
    if not message:
        return IntentResult(route="general")

    # 判断是否规划请求（复用现有逻辑）
    from src.services.agent.nodes.router import is_planning_request
    is_planning = is_planning_request(message, history)

    if not is_planning:
        return IntentResult(route="general")

    # 提取城市
    city = _extract_city(message)
    if not city and history:
        city = _extract_city_from_history(history)

    # 推荐请求（无具体城市）
    recommendation_pattern = re.compile(
        r"(推荐|建议).*(\d+月|春季|夏季|秋季|冬季|春节|暑假|寒假|国内|国外)"
    )
    if not city and recommendation_pattern.search(message):
        city = "中国"

    # 提取天数
    days = _extract_days(message)

    # 提取预算
    budget = _extract_budget(message)

    # 如果识别为规划但缺关键参数 → clarify
    if not city:
        return IntentResult(
            route="clarify",
            clarify_question="请问您想去哪个城市呢？",
        )

    return IntentResult(
        route="planning",
        city=city,
        days=days,
        budget=budget,
    )


def check_completeness(args: dict, history: Optional[list] = None) -> tuple[list[str], dict]:
    """检查 trigger_plan args 完整性。

    Args:
        args: trigger_plan 参数 {city, days, budget, departure_city, interests}
        history: 对话历史（用于继承上下文）

    Returns:
        (missing_fields, clarified_args)
        - missing_fields: 缺失字段列表（[] 表示完整）
        - clarified_args: 可从历史继承的字段值（用于补全）
    """
    missing = []
    clarified = {}

    # 城市（可从历史继承）
    city = (args.get("city") or "").strip()
    if not city:
        hist_city = _extract_city_from_history(history or [])
        if hist_city:
            clarified["city"] = hist_city
        else:
            missing.append("city")

    # 天数（不可从历史继承，必须用户明确）
    days = args.get("days")
    if not days or days <= 0:
        missing.append("days")

    # 预算（不可从历史继承，必须用户明确）
    budget = args.get("budget")
    if not budget or budget <= 0:
        missing.append("budget")

    return missing, clarified


def _build_clarify_field(key: str) -> ClarifyField:
    """构建 ClarifyField 定义。"""
    definitions = {
        "city": ClarifyField(
            key="city",
            label="目的地",
            field_type="select",
            options=CITIES[:20],
            placeholder="请输入或选择城市",
        ),
        "days": ClarifyField(
            key="days",
            label="天数",
            field_type="select",
            options=["1天", "2天", "3天", "4天", "5天", "6天", "7天"],
        ),
        "budget": ClarifyField(
            key="budget",
            label="预算（元）",
            field_type="select",
            options=["1000以下", "1000-3000", "3000-5000", "5000-10000", "10000以上"],
        ),
        "departure_city": ClarifyField(
            key="departure_city",
            label="出发城市",
            field_type="text",
            required=False,
            placeholder="可选",
        ),
    }
    return definitions.get(key, ClarifyField(key=key, label=key, field_type="text"))


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------

def _extract_city(message: str) -> Optional[str]:
    """从消息中提取城市名。"""
    for city in CITIES:
        if city in message:
            return city
    return None


def _extract_city_from_history(history: list) -> Optional[str]:
    """从对话历史中提取城市名。"""
    for msg in history:
        content = ""
        if hasattr(msg, "content") and isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        city = _extract_city(content)
        if city:
            return city
    return None


def _extract_days(message: str) -> Optional[int]:
    """从消息中提取天数。"""
    match = DAYS_PATTERN.search(message)
    if match:
        num_str = match.group(1)
        # 中文数字转换
        cn_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "两": 2}
        if num_str in cn_map:
            return cn_map[num_str]
        try:
            return int(num_str)
        except ValueError:
            pass
    return None


def _extract_budget(message: str) -> Optional[int]:
    """从消息中提取预算。"""
    match = BUDGET_PATTERN.search(message)
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return None
