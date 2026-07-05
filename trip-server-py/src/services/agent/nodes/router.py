"""Router 节点模块。

判断用户请求是规划请求还是一般对话。
迁移自 Node.js 版本的 nodes/router.ts。
"""

import re
from typing import Optional, List

# 规划请求关键词（扩大覆盖范围）
PLANNING_KEYWORDS = [
    # 核心规划词
    "规划", "行程", "几日游", "攻略", "安排", "路线", "帮我计划", "怎么玩",
    "旅游", "旅行", "出游", "度假", "自由行", "自驾游", "跟团",
    # 景点/美食/住宿
    "必去", "景点", "美食", "住宿", "酒店",
    # 推荐/建议/调整
    "推荐", "建议", "调整", "方案", "计划", "打算", "想去", "出发", "去哪",
    # 玩/去/体验
    "玩", "去", "逛", "打卡", "体验", "看看", "走走", "路过",
    # 预算/花费
    "预算", "花钱", "省钱", "穷游", "花费", "多少钱",
    # 追问词（多轮场景）
    "码头", "船票", "门票", "出发时间", "怎么去", "多远",
]

# 约束类关键词（涉及特殊需求，应进入 planning 流程以调用 retrieve_knowledge 时传入约束）
CONSTRAINT_WORDS = [
    "穆斯林", "清真", "清真餐厅", "清真美食",
    "素食", "素食主义", "不吃猪肉", "不吃肉", "吃素",
    "带宠物", "带狗", "带猫", "金毛", "柯基", "宠物", "狗", "猫",
    "带小孩", "带孩子", "亲子", "家庭", "老人", "无障碍", "婴儿", "儿童",
]

# 天气适应关键词
WEATHER_WORDS = [
    "雨", "雪", "高温", "寒冷", "台风", "雾霾", "天气", "下雨", "下雪",
    "降温", "升温", "暴雨", "大风", "雨季", "雨天",
]

# 天数模式（兼容 "3日"、"3 日"、"3天"、"3 天" 等空格变体）
DAYS_PATTERN = re.compile(r"[\d一二三四五六七八九十两]+\s*(?:日|天)|几日|几天|多少天")

# 城市名模式（2-4个汉字）
CITY_PATTERN = re.compile(r"[\u4e00-\u9fa5]{2,4}")

# 多轮修改行程模式
MODIFY_DAY_PATTERN = re.compile(r"第[一二三四五六七八九十\d]+\s*(?:日|天)")
MODIFY_INTENT = ["加", "改", "换", "调整", "删", "去掉", "换成", "加上", "安排"]


def _has_city(message: str) -> bool:
    """判断消息中是否包含城市名。"""
    return CITY_PATTERN.search(message) is not None


def _is_follow_up_in_travel_context(history: list, message: str) -> bool:
    """判断当前消息是否是在旅行规划上下文中的追问。
    
    Args:
        history: 对话历史
        message: 当前消息
        
    Returns:
        True 如果是旅行上下文中的追问
    """
    if not history:
        return False
    
    # 将历史消息拼接成文本
    history_text = ""
    for msg in history:
        content = ""
        if hasattr(msg, "content") and isinstance(msg.content, str):
            content = msg.content
        elif isinstance(msg, dict):
            content = msg.get("content", "")
        history_text += content + "\n"
    
    # 历史中有 Day 标记或行程内容（说明之前生成过行程）
    has_itinerary_in_history = re.search(
        r"Day\s*\d|第\s*\d+\s*(天|日)|行程|路线|攻略",
        history_text
    ) is not None
    
    if not has_itinerary_in_history:
        return False
    
    # 当前消息含追问词（询问细节）
    follow_up_words = [
        "刚才", "你刚才", "Day", "第", "码头", "船票", "门票", "出发",
        "多少钱", "怎么去", "多远", "多久", "几点", "哪里", "什么",
        "推荐", "建议", "哪个", "哪个更好",
    ]
    return any(w in message for w in follow_up_words)


def is_planning_request(message: str, history: Optional[list] = None) -> bool:
    """判断用户消息是否是规划请求。
    
    Args:
        message: 用户消息
        history: 对话历史（可选），用于多轮场景判断
        
    Returns:
        True 如果是规划请求，False 如果是一般对话
    """
    if not message:
        return False
    
    has_keyword = any(kw in message for kw in PLANNING_KEYWORDS)
    has_days = DAYS_PATTERN.search(message) is not None
    has_constraint = any(w in message for w in CONSTRAINT_WORDS)
    has_weather = any(w in message for w in WEATHER_WORDS)
    
    # 同时包含关键词和天数 → 规划请求
    if has_keyword and has_days:
        return True
    
    # 有规划关键词（即使没有天数）→ 规划请求
    if has_keyword:
        return True
    
    # 有天数且消息中含城市名 → 规划请求
    if has_days and _has_city(message):
        return True
    
    # 含约束关键词 → 规划请求（需要调用 retrieve_knowledge 时传入约束）
    if has_constraint:
        return True
    
    # 含天气关键词且含城市 → 规划请求（需要调用 maps_weather）
    if has_weather and _has_city(message):
        return True
    
    # 多轮修改：含"第N天" + 修改意图词 → 也算 planning
    if MODIFY_DAY_PATTERN.search(message) and any(w in message for w in MODIFY_INTENT):
        return True
    
    # 多轮场景：历史消息中含行程规划内容，当前消息是追问 → 规划请求
    if _is_follow_up_in_travel_context(history or [], message):
        return True
    
    # 推荐请求（推荐关键词 + 月份/季节，但没有具体城市）：允许进 planning 不降级
    # 例如"推荐几个国内适合 6 月去的地方"
    recommendation_without_city_pattern = re.compile(
        r"(推荐|建议).*(\d+月|春季|夏季|秋季|冬季|春节|暑假|寒假)"
    )
    if recommendation_without_city_pattern.search(message):
        has_any_planning = any(kw in message for kw in PLANNING_KEYWORDS)
        if has_any_planning:
            return True
    
    return False


def router_node(state: dict) -> dict:
    """Router 节点实现。
    
    判断用户请求类型，并更新 state 的 route 和 city 字段。
    
    Args:
        state: 当前状态
        
    Returns:
        更新的状态字段
    """
    from ..chat_graph import _extract_city_from_message, _extract_city_from_history
    
    message = state.get("message", "")
    history = state.get("conversation_history", [])
    route = "planning" if is_planning_request(message, history) else "general"
    
    # 确定城市
    city = ""
    if route == "planning":
        city = _extract_city_from_message(message)
    
    # 多轮修改场景：message 可能不包含城市名
    if route == "planning" and not city:
        city = _extract_city_from_history(history) or ""
        
        # 还找不到城市，但可能是推荐请求（推荐+月份，无具体目的地）
        # 检查消息是否为推荐请求模式
        recommendation_pattern = re.compile(
            r"(推荐|建议).*(\d+月|春季|夏季|秋季|冬季|春节|暑假|寒假|国内|国外)"
        )
        if not city and recommendation_pattern.search(message):
            # 保持 planning 路由，设置默认城市名让 planner 输出建议
            city = "中国"
            route = "planning"
        elif not city:
            route = "general"
    
    return {"route": route, "city": city}
