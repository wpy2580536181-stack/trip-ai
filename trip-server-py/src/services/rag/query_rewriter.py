"""查询改写模块.

提供本地查询改写能力，不依赖 LLM 调用：
- 提取关键词
- 移除停用词
- 可选：调用 LLM 进行查询扩展（如果对话上下文可用）
"""

import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# 中文停用词表（简化版）
_STOP_WORDS_ZH = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人",
    "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去",
    "你", "会", "着", "没有", "看", "好", "自己", "这", "但", "从",
    "可以", "这个", "当", "本", "如", "就", "让", "把", "还", "用",
    "没", "能", "过", "她", "他", "它", "们", "那", "些", "什么",
    "怎么", "如何", "为什么", "哪", "吗", "呢", "吧", "啊", "嗯",
}

# 英文停用词表（简化版）
_STOP_WORDS_EN = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "up", "about", "into", "over",
    "after", "beneath", "between", "under", "i", "me", "my", "we",
    "you", "he", "she", "it", "they", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "can", "could", "may", "might",
}

_STOP_WORDS = _STOP_WORDS_ZH.union(_STOP_WORDS_EN)


def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
    """从文本中提取关键词（基于分词和停用词过滤）.

    Args:
        text: 输入文本.
        max_keywords: 最大关键词数量.

    Returns:
        List[str]: 关键词列表，按重要性排序。

    Example:
        >>> extract_keywords("我想去北京故宫玩")
        ['北京', '故宫']
    """
    # 简单分词：按空格、标点分割
    words = re.findall(r"[\w]+", text.lower())
    # 过滤停用词和短词
    keywords = [
        w for w in words
        if w not in _STOP_WORDS and len(w) >= 2
    ]
    # 去重并保持顺序
    seen = set()
    unique_keywords = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_keywords.append(kw)
    return unique_keywords[:max_keywords]


def rewrite_query(
    query: str,
    city: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """本地查询改写（不调用 LLM）.

    对查询进行标准化处理：
    1. 移除多余空格和特殊字符
    2. 提取关键词
    3. 如果有城市信息，追加城市前缀

    Args:
        query: 原始查询文本.
        city: 目标城市（可选）.
        context: 对话上下文（可选，预留用于未来 LLM 扩展）.

    Returns:
        str: 改写后的查询文本.

    Example:
        >>> rewrite_query("我想去故宫玩", city="北京")
        '北京 故宫'
    """
    # 1. 清洗文本：保留中文、英文、数字、空格
    cleaned = re.sub(r"[^\w\s]", " ", query)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 2. 提取关键词
    keywords = extract_keywords(cleaned)

    # 3. 组装改写后的查询
    parts = []
    if city and city not in keywords:
        parts.append(city)
    parts.extend(keywords)

    rewritten = " ".join(parts) if parts else cleaned

    logger.debug("查询改写: '%s' -> '%s'", query, rewritten)
    return rewritten


async def rewrite_query_with_llm(
    query: str,
    city: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """使用 LLM 进行查询改写（可选功能）.

    当需要更复杂的查询扩展时使用，例如：
    - 同义词扩展
    - 意图理解
    - 上下文感知改写

    Args:
        query: 原始查询文本.
        city: 目标城市.
        context: 对话上下文.

    Returns:
        str: LLM 改写后的查询文本.

    Note:
        此函数需要依赖 LLM 服务，如果 LLM 不可用则降级到本地改写。
    """
    # TODO: 实现 LLM 查询改写
    # 暂时降级到本地改写
    logger.debug("LLM 查询改写未实现，降级到本地改写")
    return rewrite_query(query, city, context)


def detect_city(query: str) -> Optional[str]:
    """从查询中检测城市名称.

    Args:
        query: 查询文本.

    Returns:
        Optional[str]: 检测到的城市名，如果未检测到返回 None.

    Example:
        >>> detect_city("我想去北京玩")
        '北京'
    """
    # 只匹配已知城市名（避免误匹配）
    city_patterns = [
        r"(北京|上海|广州|深圳|成都|杭州|西安|南京|重庆|天津|武汉|苏州|厦门|昆明|三亚)",
    ]
    for pattern in city_patterns:
        match = re.search(pattern, query)
        if match:
            return match.group(1)
    return None


def detect_intent(query: str) -> str:
    """检测查询意图.

    Args:
        query: 查询文本.

    Returns:
        str: 意图类型，可选值：'scenic'（景点）、'food'（美食）、
             'hotel'（住宿）、'transport'（交通）、'general'（通用）。

    Example:
        >>> detect_intent("北京有什么好吃的")
        'food'
    """
    intent_keywords = {
        "scenic": ["景点", "景区", "好玩", "玩", "旅游", "游记", "风景"],
        "food": ["吃", "美食", "餐厅", "小吃", "特产", "好吃的"],
        "hotel": ["住", "酒店", "住宿", "民宿"],
        "transport": ["交通", "怎么去", "路线", "打车", "地铁"],
    }
    for intent, keywords in intent_keywords.items():
        if any(kw in query for kw in keywords):
            return intent
    return "general"
