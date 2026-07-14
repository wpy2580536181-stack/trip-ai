"""Token 估算工具。

中文 token 化没有精确的 BPE 映射，使用启发式估算：
- CJK 字符（中文/日文/韩文）：~1.5 字符/token
- 英文/数字/其他：~4 字符/token
- 混合文本取加权平均

精确度约 ±15%，对滑动窗口控制足够。
对齐 Node.js src/utils/tokens.ts。
"""

import math
import os

# 历史消息最大 token 数（超出则触发压缩）
DEFAULT_HISTORY_MAX_TOKENS = 16000

# 压缩后目标 token 数。把 TAIL 从 maxTokens 压到该值，
# 留出 ~25% buffer 避免下一两轮立刻又触发压缩。
DEFAULT_COMPACTION_TARGET_TOKENS = 12000


def estimate_tokens(text: str) -> int:
    """估算文本的 token 数量。

    - CJK 字符（中/日/韩）：约 1.5 字符 = 1 token
    - 其他字符（英文/数字/标点）：约 4 字符 = 1 token

    Args:
        text: 待估算文本

    Returns:
        估算 token 数，最小为 1（非空文本）
    """
    if not text:
        return 0

    cjk_count = 0
    other_count = 0

    for ch in text:
        code = ord(ch)
        if (
            (0x4E00 <= code <= 0x9FFF)    # CJK Unified Ideographs
            or (0x3400 <= code <= 0x4DBF)  # CJK Extension A
            or (0x20000 <= code <= 0x2A6DF)  # CJK Extension B
            or (0x3040 <= code <= 0x309F)  # Hiragana
            or (0x30A0 <= code <= 0x30FF)  # Katakana
        ):
            cjk_count += 1
        else:
            other_count += 1

    return max(1, math.ceil(cjk_count / 1.5 + other_count / 4))


def estimate_messages_tokens(messages: list) -> int:
    """估算消息列表的总 token 数。

    Args:
        messages: 消息列表，每条消息是 dict，包含 "content" 字段；
                  或含 .content 属性的对象

    Returns:
        总 token 数
    """
    total = 0
    for msg in messages:
        content = msg.get("content", "") if isinstance(msg, dict) else getattr(msg, "content", "")
        total += estimate_tokens(content)
    return total


def get_history_max_tokens() -> int:
    """获取历史消息最大 token 数（支持环境变量覆盖）。

    Returns:
        最大 token 数
    """
    env = os.environ.get("HISTORY_MAX_TOKENS")
    if env and env.isdigit():
        return int(env)
    return DEFAULT_HISTORY_MAX_TOKENS
