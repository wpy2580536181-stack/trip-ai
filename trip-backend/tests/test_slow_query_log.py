"""M6 阶段测试 —— SQLAlchemy 慢查询日志 hook。

覆盖 3 类：
1. >100ms 查询触发 warn log（含 SQL + duration_ms）
2. <100ms 查询不触发 warn log
3. 超长 SQL 文本被截断到 500 字符
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine


# ---------------------------------------------------------------------------
# 测试 1：>threshold 查询触发 warn log
# ---------------------------------------------------------------------------

def test_slow_query_triggers_warn_log():
    """执行慢 SQL → trip_log.warning('slow_query_detected', ...)。

    用 mock listener（SQLAlchemy 不接受 MagicMock 作为 event target，所以直接调 listener 函数）。
    模拟"200ms 前开始的 SQL"：手工往 conn.info 塞一个 200ms 前的 start_time。

    注意：structlog 不走 stdlib caplog（P0-2 已知坑），改用直接 patch trip_log 验证副作用。
    """
    from src.utils.sql_logger import _check_slow_query

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.info = {
        "sql_start_time": {id(mock_cursor): time.perf_counter() - 0.2},  # 200ms 前
    }

    with patch("src.utils.sql_logger.trip_log") as mock_log:
        _check_slow_query(mock_conn, mock_cursor, "SELECT * FROM spots", False)

    # 验证 trip_log.warning 被调用，参数正确
    mock_log.warning.assert_called_once()
    call_args = mock_log.warning.call_args
    assert call_args.args[0] == "slow_query_detected"
    assert call_args.kwargs["duration_ms"] > 100
    assert "SELECT * FROM spots" in call_args.kwargs["sql"]


# ---------------------------------------------------------------------------
# 测试 2：<threshold 查询不触发 warn log
# ---------------------------------------------------------------------------

def test_fast_query_does_not_trigger_warn():
    """执行快 SQL（<100ms）→ 不触发 warn log。"""
    from src.utils.sql_logger import _check_slow_query

    # 模拟"SQL 跑了 10ms"（<100ms 阈值）
    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.info = {
        "sql_start_time": {id(mock_cursor): time.perf_counter() - 0.01},  # 10ms 前
    }

    with patch("src.utils.sql_logger.trip_log") as mock_log:
        _check_slow_query(mock_conn, mock_cursor, "SELECT 1", False)

    # 快速 SQL 不应触发 warning
    mock_log.warning.assert_not_called()


# ---------------------------------------------------------------------------
# 测试 3：超长 SQL 文本被截断
# ---------------------------------------------------------------------------

def test_long_sql_is_truncated():
    """SQL 文本 >500 字符 → 日志里被截断（带 'truncated' 标记）。"""
    from src.utils.sql_logger import _check_slow_query, MAX_SQL_LENGTH

    # 构造 1000 字符的 SQL
    long_sql = "SELECT * FROM spots WHERE name = '" + "A" * 1000 + "'"
    assert len(long_sql) > MAX_SQL_LENGTH

    mock_cursor = MagicMock()
    mock_conn = MagicMock()
    mock_conn.info = {
        "sql_start_time": {id(mock_cursor): time.perf_counter() - 0.2},  # 200ms 前
    }

    with patch("src.utils.sql_logger.trip_log") as mock_log:
        _check_slow_query(mock_conn, mock_cursor, long_sql, False)

    mock_log.warning.assert_called_once()
    sql_text = mock_log.warning.call_args.kwargs["sql"]
    assert "truncated" in sql_text
    assert len(sql_text) < len(long_sql), "日志应比原始 SQL 短"


# ---------------------------------------------------------------------------
# 测试 4：attach 在真实 SQLite engine 上（端到端集成）
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_attach_on_real_sqlite_engine():
    """attach hook 到真实 SQLite engine，跑 SQL 验证不崩。"""
    from src.utils.sql_logger import attach_slow_query_log

    # 用 SQLite 临时 DB（跟 e2e_m1 一样）
    engine = create_engine("sqlite:///:memory:", echo=False)

    # attach hook
    attach_slow_query_log(engine, threshold_ms=100)

    # 跑 SQL（应该正常执行不崩）
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

    # 跑超长 SQL 也不应崩
    with engine.connect() as conn:
        long_sql = "SELECT '" + "X" * 1000 + "'"
        result = conn.execute(text(long_sql))
        assert result.scalar() == "X" * 1000
