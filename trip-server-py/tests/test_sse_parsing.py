"""SSE 流端到端解析测试

测试 SSE 事件格式生成 + 流解析逻辑。

覆盖：
- sse_event() 格式正确（data: JSON\\n\\n）
- sse_end_event() 格式正确
- sse_error_event() 格式正确
- 完整 SSE 流模拟：chunk → chunk → tool_start → tool_end → chunk → complete
- 从 SSE 流中提取 conversation_id
- 从 SSE 流中提取 usage/tokens
- 心跳事件处理
- 错误事件处理
- 多事件拼接后正确解析
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from src.utils.stream import sse_end_event, sse_error_event, sse_event


# ===================================================================
# sse_event() / sse_end_event() / sse_error_event() 格式
# ===================================================================


class TestSSEEventFormat:
    """SSE 事件格式测试。"""

    def test_sse_event_basic(self):
        """sse_event 输出 data: JSON\\n\\n 格式。"""
        result = sse_event({"type": "chunk", "content": "hello"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")
        # 解析 JSON
        data_str = result.strip().replace("data: ", "")
        parsed = json.loads(data_str)
        assert parsed == {"type": "chunk", "content": "hello"}

    def test_sse_event_with_event_id(self):
        """sse_event 带 event_id 时包含 id: 行。"""
        result = sse_event({"type": "chunk", "content": "hi"}, event_id=42)
        assert "id: 42\n" in result
        assert "data: " in result
        assert result.endswith("\n\n")

    def test_sse_event_with_event_name(self):
        """sse_event 带 event name 时包含 event: 行。"""
        result = sse_event({"type": "chunk"}, event="message")
        assert "event: message\n" in result

    def test_sse_event_chinese_not_escaped(self):
        """中文不被 ASCII 转义。"""
        result = sse_event({"type": "chunk", "content": "你好"})
        assert "你好" in result
        assert "\\u" not in result

    def test_sse_end_event_format(self):
        """sse_end_event 格式正确。"""
        result = sse_end_event()
        assert "event: end\n" in result
        assert 'data: {"done":true}' in result
        assert result.endswith("\n\n")

    def test_sse_error_event_format(self):
        """sse_error_event 格式正确。"""
        result = sse_error_event("something went wrong")
        assert "event: error\n" in result
        assert result.endswith("\n\n")
        # 解析 data 中的 JSON
        data_line = [l for l in result.split("\n") if l.startswith("data: ")][0]
        parsed = json.loads(data_line.replace("data: ", ""))
        assert parsed["type"] == "error"
        assert parsed["error"] == "something went wrong"


# ===================================================================
# SSE 流解析（使用 real_agent.py 中的解析函数）
# ===================================================================


class TestSSEStreamParsing:
    """模拟完整 SSE 流并解析。"""

    def _build_sse_stream(self, events: list[dict]) -> str:
        """将一系列事件字典拼接成 SSE 文本流。"""
        parts = []
        for ev in events:
            parts.append(sse_event(ev))
        parts.append(sse_end_event())
        return "".join(parts)

    def _parse_events_from_text(self, text: str) -> list[dict]:
        """从 SSE 文本流中解析出所有事件（跳过 end/done 事件）。"""
        events = []
        buffer = text
        while "\n\n" in buffer:
            idx = buffer.index("\n\n")
            raw = buffer[:idx]
            buffer = buffer[idx + 2:]
            if not raw.strip():
                continue
            data_lines = []
            for line in raw.split("\n"):
                if line.startswith("data:"):
                    data_lines.append(line[5:].strip())
            if not data_lines:
                continue
            data_str = "\n".join(data_lines)
            try:
                parsed = json.loads(data_str)
                # 跳过 end/done 事件
                if isinstance(parsed, dict) and parsed.get("done") is True:
                    continue
                events.append(parsed)
            except json.JSONDecodeError:
                pass
        return events

    @pytest.mark.asyncio
    async def test_full_stream_simulation(self):
        """完整 SSE 流：chunk → chunk → tool_start → tool_end → chunk → complete。"""
        stream_events = [
            {"type": "chunk", "content": "Hello "},
            {"type": "chunk", "content": "world"},
            {"type": "tool_start", "name": "search_hotels"},
            {"type": "tool_end", "name": "search_hotels"},
            {"type": "chunk", "content": "!"},
            {
                "type": "complete",
                "data": {"conversationId": 42},
                "usage": {"prompt": 100, "completion": 50, "total": 150, "cached": 30},
            },
        ]
        text = self._build_sse_stream(stream_events)
        events = self._parse_events_from_text(text)

        # 验证事件类型顺序
        types = [e["type"] for e in events]
        assert types == ["chunk", "chunk", "tool_start", "tool_end", "chunk", "complete"]

        # 验证文本拼接
        chunks = [e["content"] for e in events if e["type"] == "chunk"]
        assert "".join(chunks) == "Hello world!"

    def test_extract_conversation_id(self):
        """从 SSE 流中提取 conversation_id。"""
        stream_events = [
            {"type": "chunk", "content": "hi"},
            {"type": "complete", "data": {"conversationId": 123}},
        ]
        text = self._build_sse_stream(stream_events)
        events = self._parse_events_from_text(text)

        complete_event = [e for e in events if e["type"] == "complete"][0]
        assert complete_event["data"]["conversationId"] == 123

    def test_extract_usage_tokens(self):
        """从 SSE 流中提取 usage/tokens。"""
        usage_data = {"prompt": 1234, "completion": 567, "total": 1801, "cached": 400}
        stream_events = [
            {"type": "chunk", "content": "result"},
            {"type": "complete", "data": {"conversationId": 1}, "usage": usage_data},
        ]
        text = self._build_sse_stream(stream_events)
        events = self._parse_events_from_text(text)

        complete_event = [e for e in events if e["type"] == "complete"][0]
        assert complete_event["usage"]["prompt"] == 1234
        assert complete_event["usage"]["completion"] == 567
        assert complete_event["usage"]["total"] == 1801
        assert complete_event["usage"]["cached"] == 400

    def test_heartbeat_event_handling(self):
        """心跳事件（空 data）不破坏解析。

        SSE 协议允许空行作为心跳/keep-alive。
        """
        # 模拟心跳：在正常事件之间插入空行
        parts = [
            sse_event({"type": "chunk", "content": "A"}),
            "\n\n",  # 心跳
            sse_event({"type": "chunk", "content": "B"}),
            sse_end_event(),
        ]
        text = "".join(parts)
        events = self._parse_events_from_text(text)

        chunks = [e for e in events if e.get("type") == "chunk"]
        assert len(chunks) == 2
        assert chunks[0]["content"] == "A"
        assert chunks[1]["content"] == "B"

    def test_error_event_parsing(self):
        """错误事件处理。"""
        error_text = sse_error_event("rate limit exceeded")
        events = self._parse_events_from_text(error_text)

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["error"] == "rate limit exceeded"

    def test_multi_event_concatenation(self):
        """多事件拼接后正确解析。"""
        events_a = [
            {"type": "chunk", "content": "part1"},
            {"type": "complete", "data": {"conversationId": 10}},
        ]
        events_b = [
            {"type": "chunk", "content": "part2"},
            {"type": "complete", "data": {"conversationId": 20}},
        ]
        # 拼接两个流
        text = self._build_sse_stream(events_a) + self._build_sse_stream(events_b)
        parsed = self._parse_events_from_text(text)

        chunks = [e for e in parsed if e.get("type") == "chunk"]
        completes = [e for e in parsed if e.get("type") == "complete"]
        assert len(chunks) == 2
        assert len(completes) == 2
        assert completes[0]["data"]["conversationId"] == 10
        assert completes[1]["data"]["conversationId"] == 20

    def test_tool_start_end_pairing(self):
        """tool_start / tool_end 配对。"""
        stream_events = [
            {"type": "tool_start", "name": "retrieve_knowledge"},
            {"type": "tool_end", "name": "retrieve_knowledge"},
            {"type": "tool_start", "name": "search_hotels"},
            {"type": "tool_end", "name": "search_hotels"},
        ]
        text = self._build_sse_stream(stream_events)
        events = self._parse_events_from_text(text)

        starts = [e for e in events if e["type"] == "tool_start"]
        ends = [e for e in events if e["type"] == "tool_end"]
        assert len(starts) == 2
        assert len(ends) == 2
        assert starts[0]["name"] == "retrieve_knowledge"
        assert starts[1]["name"] == "search_hotels"

    def test_event_with_id_field(self):
        """带 id 字段的事件正确解析。"""
        result = sse_event({"type": "chunk", "content": "x"}, event_id=5)
        events = self._parse_events_from_text(result)
        assert len(events) == 1
        assert events[0]["type"] == "chunk"
        assert events[0]["content"] == "x"

    def test_large_payload(self):
        """大 payload 正确解析。"""
        large_content = "x" * 10000
        stream_events = [
            {"type": "chunk", "content": large_content},
            {"type": "complete", "data": {"conversationId": 1}},
        ]
        text = self._build_sse_stream(stream_events)
        events = self._parse_events_from_text(text)

        chunks = [e for e in events if e.get("type") == "chunk"]
        assert len(chunks) == 1
        assert len(chunks[0]["content"]) == 10000
