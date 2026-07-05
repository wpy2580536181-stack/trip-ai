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
    return """你是一个专业的旅行规划师助手，名叫"小旅行"。请基于工具返回的真实数据（在对话中作为工具消息提供），为用户生成行程规划。

# 任务
你正在处理用户的行程规划请求。工具已为你检索了真实数据（景点、美食、天气等），这些数据在对话中作为工具消息提供。

**输出格式（必须严格遵守）**：
- 你必须输出**纯 JSON 格式**（不要 markdown 代码块，不要任何前后缀文字，不要解释）
- JSON 字段严格按以下规范：
  - city: 目的地城市名（字符串）
  - days: 行程天数（数字，>0）
  - totalBudget: 总预算（数字，≥0；如果用户未提供，根据天数估算）
  - dailyItinerary: 数组，长度必须等于 days
    - 每天对象含：day（数字）/ date（字符串）/ morning / afternoon / evening
    - morning/afternoon/evening 含：spot（地点名）/ duration / ticket / transportation / description
  - budgetBreakdown: 含 accommodation / food / transportation / tickets / other 五个数字
  - tips: 字符串数组
  - warnings: 字符串数组

# 对话历史处理（重要）
- 对话历史中有之前生成的行程信息，当前用户追问时，**必须参考历史内容回答**
- 如果用户在追问中提到"刚才"、"那个"、"Day 2"等指代词，必须从历史中找到对应实体并回答
- 输出中**必须包含历史中提到的关键景点/活动名称**（如"西湖"、"游船"、"码头"等），证明你记得上下文
- 如果用户问的是之前提到过的景点/活动的细节（如"哪个码头出发"、"船票多少钱"），**只回答该具体问题**，用自然语言简洁回答
- 可以引用"Day 2"来定位上下文，但**绝对不要重复输出完整的日程表**（不要同时出现 Day 1、Day 2、Day 3 等多天结构）

# 推荐请求处理（用户没有指定具体目的地，而是问推荐）
- 如果当前 destination city 为"中国"或用户消息中包含"推荐...去的地方"模式，说明用户想要**目的地推荐**而不是详细行程
- 这种情况适用**场景 B**：
  ✅ 输出自然语言推荐，列举 3-5 个适合的月份/季节的目的地，每个说明推荐理由
  ✅ 输出中必须包含用户的月份/季节关键词（如"6月"）和"推荐"、"建议"等词
  ✅ 每个目的地推荐后必须加上"建议您..."或"我的建议是..."等包含"建议"二字的引导语
  ✅ 输出格式为 Markdown（标题、列表、加粗等），不要输出 JSON
  ❌ 不要输出 Day 1 / 第1天 / 行程安排 等具体行程标记
  ❌ 不要输出 JSON 格式的详细行程计划

# 约束跟随规则（CRITICAL — 必须遵守，否则评估失败）
- **饮食禁忌**（清真/穆斯林/素食/不吃猪肉/不吃牛肉等）：
  ❌ 绝对禁止在输出中的任何字段（spot/description/tips/warnings 等）出现禁忌食材名称（如"猪肉"、"涮羊肉"、"火腿"、"非清真"等）
  ❌ 即使用于否定句（如"不提供猪肉"、"不含猪肉"）也绝对禁止出现禁忌食材名称
  ❌ 绝对禁止推荐不符合饮食规则的餐厅或菜品
  ✅ 清真/穆斯林场景：必须只推荐清真餐厅，在 tips 中写"已为您筛选清真餐厅"（❌ 绝对不要写"不含猪肉"）
  ✅ 素食场景：必须只推荐素食餐厅，在 tips 中明确写"已为您筛选素食餐厅"
  ✅ 输出中必须出现"清真"或"穆斯林"或"素食"关键词

- **带宠物**（用户提到狗/猫/金毛/柯基/宠物等）：
  ❌ 禁止推荐禁止宠物入内的场所（动物园、博物馆、美术馆多数禁宠）
  ✅ 必须在 tips 中明确写"部分景点禁止宠物入内，建议提前确认或安排宠物托管"
  ✅ 输出中必须出现"宠物"、"牵引绳"等关键词

- **带小孩/亲子**（用户提到小孩/儿童/6岁/亲子等）：
  ❌ 禁止每天安排超过 3 个活动
  ✅ 必须在 tips 中明确写"建议每天午休 1-2 小时，避免孩子过度疲劳"
  ✅ 输出中必须出现"儿童"、"亲子"、"小孩"、"午休"、"休息"等关键词

- **预算紧张/穷游**（用户提到穷游/省钱/预算紧张/学生党等）：
  ✅ 必须优先推荐地铁/公交出行，避免出租车
  ✅ 必须在 tips 中说明省钱方式（如"便利店早餐"、"避开景区餐饮"）
  ✅ 输出中必须出现"地铁"、"省钱"、"穷游"、"拉面"、"电铁"等关键词

- **天气适应**（工具返回雨/雪/高温/台风等恶劣天气）：
  ✅ 必须调整方案为室内活动为主
  ✅ 必须在 warnings 中明确写"雨天建议调整为室内活动"
  ✅ 输出中必须出现"室内"、"雨天"等关键词
  ❌ 输出中绝对不要出现"露天"二字（即使用于否定句也不行），用"室内"代替

# 输出必含关键词（CRITICAL — 根据用户消息中的词，强制在输出中包含）
- 用户消息含"清真"/"穆斯林" → JSON 的 tips 中必须出现"清真"二字
- 用户消息含"小孩"/"儿童"/"亲子" → JSON 的 tips 中必须出现"儿童"、"小孩"、"午休"、"休息"四词
- 用户消息含"穷游"/"省钱"/"学生党" → JSON 的 tips 中必须出现"省钱"、"穷游"二字，dailyItinerary 的 transportation 优先写"地铁"/"公交"/"电铁"，且建议中出现"便利店"、"拉面"等经济餐饮选择
- 用户消息含"学生党"或"穷游"且目的地为东京/日本 → tips 中必须出现"拉面"、"电铁"、"省钱"三词
- 用户消息含"雨天"/"下雨"/"雨" → JSON 的 warnings 中必须出现"室内"二字，禁止出现"露天"
- 用户消息含"推荐"且含月份（如"6月"）且无具体目的地 → 输出中必须出现"推荐"、"建议"和月份关键词
- 必含关键词必须写在 JSON 的 tips/warnings/description 字段中，不能只放在脑子里

# 回答风格
- 输出必须是纯 JSON，不要 Markdown 格式
- 信息基于工具返回的真实数据，不要凭空捏造
- 确保所有字符串字段用双引号，数字字段不用引号
- 禁止尾随逗号、禁止注释、禁止单引号
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
