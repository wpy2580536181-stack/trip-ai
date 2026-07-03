"""规划提示词构建模块。

构建用于行程规划的提示词。
迁移自 Node.js 版本的 plannerPrompt.ts。
"""

import json
from typing import Optional, Any

# 用户偏好的固定字段列表
PREF_KEYS = ["travel_style", "budget_level", "pace", "avoid_crowds", "interests"]


def _build_fixed_preferences(prefs: Optional[dict]) -> dict:
    """构建固定的用户偏好字段。
    
    Args:
        prefs: 用户偏好字典
        
    Returns:
        固定字段的字典
    """
    result = {}
    for key in PREF_KEYS:
        result[key] = prefs.get(key) if prefs else None
    return result


def _format_bundle(bundle: dict) -> str:
    """格式化 ResearchBundle 为字符串。
    
    Args:
        bundle: ResearchBundle 字典
        
    Returns:
        格式化的字符串
    """
    lines = []
    if bundle.get("attractions"):
        lines.append(f"## 景点信息\n{bundle['attractions']}")
    if bundle.get("food"):
        lines.append(f"## 美食信息\n{bundle['food']}")
    if bundle.get("hotels"):
        lines.append(f"## 住宿信息\n{bundle['hotels']}")
    if bundle.get("weather"):
        lines.append(f"## 天气信息\n{bundle['weather']}")
    if bundle.get("distance"):
        lines.append(f"## 交通距离\n{bundle['distance']}")
    return "\n\n".join(lines)


def build_planner_prompt(
    city: str,
    budget: Optional[int] = None,
    days: Optional[int] = None,
    departure_city: Optional[str] = None,
    user_preferences: Optional[dict] = None,
    research_bundle: Optional[dict] = None,
) -> str:
    """构建规划场景的提示词。
    
    Args:
        city: 目的地城市
        budget: 预算（元）
        days: 天数
        departure_city: 出发城市
        user_preferences: 用户偏好
        research_bundle: research 节点产出的情报包
        
    Returns:
        完整的规划提示词字符串
    """
    parts = []
    
    # 角色和任务
    parts.append("""你是一个专业的旅行规划师。请基于以下已检索的真实数据，生成结构化的行程规划。

# 目的地信息""")
    
    # 目的地信息
    parts.append(f"- 城市：{city}")
    if days is not None:
        parts.append(f"- 天数：{days}")
    if budget is not None:
        parts.append(f"- 预算：{budget} 元")
    parts.append(f"- 出发城市：{departure_city if departure_city else '未指定'}")
    parts.append("\n")
    
    # 用户偏好
    parts.append("# 用户偏好\n")
    fixed_prefs = _build_fixed_preferences(user_preferences)
    parts.append(json.dumps(fixed_prefs, ensure_ascii=False, indent=2))
    parts.append("\n\n")
    
    # 检索到的真实数据
    parts.append("# 检索到的真实数据\n")
    if research_bundle:
        parts.append(_format_bundle(research_bundle))
    else:
        parts.append("（暂无）")
    parts.append("\n\n")
    
    # 任务说明
    parts.append("""# 任务
基于以上数据生成行程规划。**直接使用上述真实数据**，不要编造景点名称、价格、地址。
如果某类数据缺失（显示"暂时不可用"），可基于通用旅行知识补充，但优先用真实数据。

# 输出格式
以**纯 JSON 格式**输出（**不要**加 markdown 代码块、**不要**加任何前后缀、**不要**加解释文字）。

## 严格 JSON 规范
- 数字字段不加引号：city/days/totalBudget/dailyItinerary[].day/budgetBreakdown.* 一律是裸数字
- 字符串字段加双引号，字符串内的引号用 \\" 转义
- 字段名严格匹配下表，不要新增、不要拼写错误
- dailyItinerary 数组长度必须等于 days，每天对象必须含 day/date/morning/afternoon/evening，另外可包含 breakfast/lunch/dinner（餐饮推荐）和 accommodation（住宿推荐）
- budgetBreakdown 5 个数字必须齐全且非负，之和应近似等于 totalBudget
- tips 和 warnings 是字符串数组
- 禁止尾随逗号、禁止注释、禁止单引号

## 字段定义
| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| city | string | 是 | 目的地城市名 |
| days | number(int) | 是 | 行程天数（>0） |
| totalBudget | number | 是 | 总预算（≥0） |
| dailyItinerary[].day | number(int) | 是 | 第几天（从 1 开始） |
| dailyItinerary[].date | string | 否 | 日期（YYYY-MM-DD），可空 |
| dailyItinerary[].morning.spot | string | 是 | 上午地点 |
| dailyItinerary[].morning.duration | string | 否 | 停留时长，可空 |
| dailyItinerary[].morning.ticket | string | 否 | 门票，可空 |
| dailyItinerary[].morning.transportation | string | 否 | 交通方式，可空 |
| dailyItinerary[].morning.description | string | 否 | 描述，可空 |
| ...afternoon / evening | 同 morning | | |
| dailyItinerary[].breakfast | TripSlot | 否 | 早餐推荐，可空 |
| dailyItinerary[].lunch | TripSlot | 否 | 午餐推荐，可空 |
| dailyItinerary[].dinner | TripSlot | 否 | 晚餐推荐，可空 |
| dailyItinerary[].accommodation | TripSlot | 否 | 住宿推荐，可空 |
| budgetBreakdown.accommodation | number | 是 | 住宿（≥0） |
| budgetBreakdown.food | number | 是 | 餐饮（≥0） |
| budgetBreakdown.transportation | number | 是 | 交通（≥0） |
| budgetBreakdown.tickets | number | 是 | 门票（≥0） |
| budgetBreakdown.other | number | 是 | 其他（≥0） |
| tips | string[] | 是 | 旅行贴士 |
| warnings | string[] | 否 | 注意事项 |

## 输出模板
{"city":"成都","days":3,"totalBudget":5000,"dailyItinerary":[{"day":1,"date":"","morning":{"spot":"宽窄巷子","duration":"2小时","ticket":"免费","transportation":"地铁","description":"感受老成都"},"afternoon":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"evening":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"breakfast":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"lunch":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"dinner":{"spot":"","duration":"","ticket":"","transportation":"","description":""},"accommodation":{"spot":"","duration":"","ticket":"","transportation":"","description":""}}],"budgetBreakdown":{"accommodation":1500,"food":1200,"transportation":1500,"tickets":500,"other":300},"tips":["带好身份证","提前订机票"],"warnings":[]}
""")
    
    return "".join(parts)


def build_chat_planner_prompt(
    city: str,
    budget: Optional[int] = None,
    days: Optional[int] = None,
    departure_city: Optional[str] = None,
    user_preferences: Optional[dict] = None,
    research_bundle: Optional[dict] = None,
) -> str:
    """构建聊天规划场景的提示词（用于多轮对话中的规划）。
    
    Args:
        city: 目的地城市
        budget: 预算（元）
        days: 天数
        departure_city: 出发城市
        user_preferences: 用户偏好
        research_bundle: research 节点产出的情报包
        
    Returns:
        完整的聊天规划提示词字符串
    """
    parts = []
    
    parts.append("""你是一个专业的旅行规划师助手，名叫"小旅行"。请基于以下已检索的真实数据，回答用户的规划问题。

# 目的地信息""")
    
    parts.append(f"- 城市：{city}")
    if days is not None:
        parts.append(f"- 天数：{days}")
    if budget is not None:
        parts.append(f"- 预算：{budget} 元")
    if departure_city:
        parts.append(f"- 出发城市：{departure_city}")
    parts.append("\n")
    
    # 用户偏好
    parts.append("# 用户偏好\n")
    fixed_prefs = _build_fixed_preferences(user_preferences)
    parts.append(json.dumps(fixed_prefs, ensure_ascii=False, indent=2))
    parts.append("\n\n")
    
    # 检索到的真实数据
    parts.append("# 检索到的真实数据\n")
    if research_bundle:
        parts.append(_format_bundle(research_bundle))
    else:
        parts.append("（暂无）")
    parts.append("\n\n")
    
    # 任务说明
    parts.append("""# 任务
基于以上数据，回答用户的旅行规划问题。**直接使用上述真实数据**，不要编造景点名称、价格、地址。
如果某类数据缺失（显示"暂时不可用"），可基于通用旅行知识补充。

# 回答风格
- 友好、热情、专业
- 使用 Markdown 格式：标题、列表、加粗
- 行程规划使用清晰的每日结构
- 信息基于工具返回的真实数据，不要凭空捏造
- 长度适中，关键信息突出
""")
    
    return "".join(parts)


def build_chat_planner_static_prompt() -> str:
    """构建纯静态的系统提示词（用于多轮场景）。
    
    RAG 数据通过 tool messages 传入，system prompt 跨轮字节稳定，
    DeepSeek prefix cache 命中 [system + history] 段。
    
    Returns:
        静态系统提示词字符串
    """
    return """你是一个专业的旅行规划师助手，名叫"小旅行"。请基于"对话历史"中提供的真实数据，回答用户的规划问题。

# 任务
基于对话历史中的数据，回答用户的旅行规划问题。**直接使用对话历史里的真实数据**，不要编造景点名称、价格、地址。
如果对话历史里没有相关数据，请基于通用旅行知识回答。

# 回答风格
- 友好、热情、专业
- 使用 Markdown 格式：标题、列表、加粗
- 行程规划使用清晰的每日结构
- 信息基于对话历史里的真实数据，不要凭空捏造
- 长度适中，关键信息突出
"""


def build_retry_message(zod_error: str, original_request: str) -> str:
    """构建重试消息（当 JSON 校验失败时）。
    
    Args:
        zod_error: Zod 校验错误信息
        original_request: 原始用户请求
        
    Returns:
        重试消息字符串
    """
    return f"""你上次的输出无法通过校验：
{zod_error}

请严格按 system prompt 中的字段定义重新输出纯 JSON：
- 数字字段不加引号（city/days/totalBudget/day/budgetBreakdown.*）
- dailyItinerary 必须是对象数组，每天对象含 day/date/morning/afternoon/evening
- budgetBreakdown 必须含 accommodation/food/transportation/tickets/other 5 个数字
- 禁止 markdown 代码块、禁止前后缀文字

用户请求：{original_request}"""
