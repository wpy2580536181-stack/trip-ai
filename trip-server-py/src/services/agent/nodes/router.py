"""Router 节点模块。

判断用户请求是规划请求还是一般对话。
迁移自 Node.js 版本的 nodes/router.ts。
"""

import re
from typing import Optional

# 规划请求关键词
PLANNING_KEYWORDS = ["规划", "行程", "几日游", "攻略", "安排", "路线", "帮我计划", "怎么玩"]

# 天数模式（兼容 "3日"、"3 日"、"3天"、"3 天" 等空格变体）
DAYS_PATTERN = re.compile(r"[\d一二三四五六七八九十两]+\s*(?:日|天)|几日|几天|多少天")

# 多轮修改行程模式
MODIFY_DAY_PATTERN = re.compile(r"第[一二三四五六七八九十\d]+\s*(?:日|天)")
MODIFY_INTENT = ["加", "改", "换", "调整", "删", "去掉", "换成", "加上", "安排"]


def is_planning_request(message: str) -> bool:
    """判断用户消息是否是规划请求。
    
    Args:
        message: 用户消息
        
    Returns:
        True 如果是规划请求，False 如果是一般对话
    """
    if not message:
        return False
    
    # 同时包含关键词和天数 → 规划请求
    has_keyword = any(kw in message for kw in PLANNING_KEYWORDS)
    has_days = DAYS_PATTERN.search(message) is not None
    if has_keyword and has_days:
        return True
    
    # 多轮修改：含"第N天" + 修改意图词 → 也算 planning
    if MODIFY_DAY_PATTERN.search(message) and any(w in message for w in MODIFY_INTENT):
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
    route = "planning" if is_planning_request(message) else "general"
    
    # 确定城市
    city = ""
    if route == "planning":
        city = _extract_city_from_message(message)
    
    # 多轮修改场景：message 可能不包含城市名
    if route == "planning" and not city:
        history = state.get("conversation_history", [])
        city = _extract_city_from_history(history) or ""
        
        # 还找不到：回退到 general 由 legacy agent 处理
        if not city:
            route = "general"
    
    return {"route": route, "city": city}
