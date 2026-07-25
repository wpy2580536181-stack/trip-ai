"""SQLAlchemy 慢查询日志（M6 新增）。

设计：
- 用 SQLAlchemy event hook（before_cursor_execute + after_cursor_execute）记录每次 SQL 耗时
- 超过阈值（默认 100ms）触发 trip_log.warning
- 日志包含：截断的 SQL 文本（500 字符）、耗时
- attach 在 init_db() 之后（必须先有 engine）

面试故事：
- "我项目里用 SQLAlchemy event hook 自动捕获 >100ms 的慢查询，输出结构化日志"
- "能直接看 trip_log 的 JSON 日志定位慢查询，零额外配置"
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import Engine

from src.utils.logger import trip_log


# 慢查询阈值（毫秒）—— 默认 100ms，可通过 attach_slow_query_log(threshold_ms=...) 调整
DEFAULT_SLOW_QUERY_THRESHOLD_MS = 100

# SQL 文本最大长度（避免日志爆掉）
MAX_SQL_LENGTH = 500

# 模块级变量保存阈值（attach 时设置，listener 闭包引用）
_slow_query_threshold_ms: int = DEFAULT_SLOW_QUERY_THRESHOLD_MS


# ---------------------------------------------------------------------------
# Listener 函数（模块级，测试可直接调）
# ---------------------------------------------------------------------------

def _record_start_time(conn: Any, cursor: Any) -> None:
    """SQL 执行前：记录开始时间。"""
    conn.info.setdefault("sql_start_time", {})[id(cursor)] = time.perf_counter()


def _check_slow_query(conn: Any, cursor: Any, statement: str, executemany: bool) -> None:
    """SQL 执行后：计算耗时，超过阈值触发 warn log。"""
    start_times = conn.info.get("sql_start_time", {})
    start_time = start_times.pop(id(cursor), None)
    if start_time is None:
        return  # 没有 start_time（不应发生）

    duration_ms = (time.perf_counter() - start_time) * 1000

    if duration_ms >= _slow_query_threshold_ms:
        # 截断 SQL 避免日志爆掉
        sql_text = statement[:MAX_SQL_LENGTH]
        if len(statement) > MAX_SQL_LENGTH:
            sql_text += f"... (truncated, total {len(statement)} chars)"

        trip_log.warning(
            "slow_query_detected",
            duration_ms=round(duration_ms, 2),
            threshold_ms=_slow_query_threshold_ms,
            sql=sql_text,
            executemany=executemany,
        )


# ---------------------------------------------------------------------------
# 注册接口
# ---------------------------------------------------------------------------

def attach_slow_query_log(engine: Engine, threshold_ms: int = DEFAULT_SLOW_QUERY_THRESHOLD_MS) -> None:
    """给 SQLAlchemy engine 装慢查询日志 hook。

    Args:
        engine: SQLAlchemy **sync** engine（async engine 用 `engine.sync_engine` 转）
        threshold_ms: 慢查询阈值（毫秒，默认 100）
    """
    global _slow_query_threshold_ms
    _slow_query_threshold_ms = threshold_ms

    def _before(conn, cursor, statement, parameters, context, executemany):
        _record_start_time(conn, cursor)

    def _after(conn, cursor, statement, parameters, context, executemany):
        _check_slow_query(conn, cursor, statement, executemany)

    event.listens_for(engine, "before_cursor_execute")(_before)
    event.listens_for(engine, "after_cursor_execute")(_after)
