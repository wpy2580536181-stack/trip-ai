"""structlog 配置（对齐 Node.js pino）"""

import structlog
import logging


def setup_logging():
    """配置 structlog（对齐 Node.js pino 的 JSON 输出）"""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(level=logging.INFO)


# 命名 logger（对齐 Node.js 的命名 logger）
logger = structlog.get_logger()
trip_log = structlog.get_logger("trip")
stream_log = structlog.get_logger("stream")
agent_log = structlog.get_logger("agent")
redis_log = structlog.get_logger("redis")
knowledge_log = structlog.get_logger("knowledge")
