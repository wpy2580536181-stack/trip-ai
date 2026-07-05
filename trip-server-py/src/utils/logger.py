"""structlog 配置（对齐 Node.js pino）

功能：
- JSON 输出（与 Node.js pino 一致）
- 敏感字段脱敏（password / token / api_key / email / authorization / cookie）
- 16 个命名 logger（对齐 Node.js 子 logger）
"""

from __future__ import annotations

import logging
import re
from typing import Any

import structlog


# ---------------------------------------------------------------------------
# 敏感字段脱敏 processor（简单字符串替换，不影响性能）
# ---------------------------------------------------------------------------

# 需要在 event dict 中检查并脱敏的字段名（小写匹配）
_SENSITIVE_KEYS = frozenset({
    "password",
    "token",
    "api_key",
    "apikey",
    "secret",
    "authorization",
    "cookie",
    "email",
    "access_token",
    "refresh_token",
    "private_key",
})

_REDACTED = "[REDACTED]"

# 用于扫描字符串值中疑似包含 token/key 的模式（Bearer xxx / sk-xxx）
_BEARER_RE = re.compile(r"(Bearer\s+)\S+", re.IGNORECASE)
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9]{16,}")


def _redact_processor(
    logger: logging.Logger, method_name: str, event_dict: dict
) -> dict:
    """structlog processor：对 event_dict 中的敏感字段进行脱敏。

    - 键名命中 _SENSITIVE_KEYS → 值替换为 [REDACTED]
    - 字符串值中包含 Bearer / sk- 模式 → 局部替换
    """
    for key in list(event_dict.keys()):
        key_lower = key.lower()
        if key_lower in _SENSITIVE_KEYS:
            event_dict[key] = _REDACTED
        else:
            val = event_dict[key]
            if isinstance(val, str):
                val = _BEARER_RE.sub(r"\1" + _REDACTED, val)
                val = _SK_RE.sub(_REDACTED, val)
                event_dict[key] = val
    return event_dict


# ---------------------------------------------------------------------------
# 初始化
# ---------------------------------------------------------------------------


def setup_logging(level: str = "INFO") -> None:
    """配置 structlog（对齐 Node.js pino 的 JSON 输出 + 敏感字段脱敏）。

    Args:
        level: 日志级别（默认 INFO；开发环境建议 DEBUG）
    """
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # 敏感字段脱敏（放在序列化之前）
            _redact_processor,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO))


# ---------------------------------------------------------------------------
# 命名 logger（对齐 Node.js pino child logger）
# ---------------------------------------------------------------------------

# Node.js 命名:
#   agent / trip / knowledge / user / auth / summary / queryRewrite /
#   reranker / embedding / stream / llmGuard / chroma / http / feedback /
#   redis / alert

logger = structlog.get_logger()

agent_log = structlog.get_logger("agent")
trip_log = structlog.get_logger("trip")
knowledge_log = structlog.get_logger("knowledge")
user_log = structlog.get_logger("user")
auth_log = structlog.get_logger("auth")
summary_log = structlog.get_logger("summary")
query_rewrite_log = structlog.get_logger("queryRewrite")
reranker_log = structlog.get_logger("reranker")
embedding_log = structlog.get_logger("embedding")
stream_log = structlog.get_logger("stream")
llm_guard_log = structlog.get_logger("llmGuard")
chroma_log = structlog.get_logger("chroma")
http_log = structlog.get_logger("http")
feedback_log = structlog.get_logger("feedback")
redis_log = structlog.get_logger("redis")
alert_log = structlog.get_logger("alert")
