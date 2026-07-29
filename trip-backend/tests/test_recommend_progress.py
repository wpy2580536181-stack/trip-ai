"""行程生成进度可视化链路测试

覆盖：
- Orchestrator.plan 各阶段 progress 事件（research/plan/review + 重试轮次）
- trip_controller._recommend_stream 透传 progress/tool 事件且先于 complete
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.agent.agents.base_agent import AgentOutput
from src.services.agent.orchestrator import Orchestrator
from src.services.agent.schemas import PlanRequest, ResearchBundle
from src.services.agent.review import ReviewResult


FAKE_PLAN = {"city": "上海", "days": 5, "dailyItinerary": [], "budgetBreakdown": {}}


def _make_orchestrator(events: list) -> Orchestrator:
    async def on_event(e):
        events.append(e)

    orch = Orchestrator(llm=MagicMock(), on_event=on_event)
    orch.research_agent = MagicMock()
    orch.research_agent.run = AsyncMock(return_value=AgentOutput(
        agent_name="research", result=ResearchBundle(), duration_ms=3000,
    ))
    orch.planner_agent = MagicMock()
    orch.planner_agent.run = AsyncMock(return_value=AgentOutput(
        agent_name="planner", result='{"city": "上海"}', duration_ms=20000,
    ))
    return orch


def _progress_of(events: list) -> list[tuple]:
    return [
        (e["data"]["stage"], e["data"]["status"])
        for e in events if e.get("type") == "progress"
    ]


class TestOrchestratorProgress:

    @pytest.mark.asyncio
    async def test_plan_emits_stage_progress(self):
        """一次通过：research/plan/review 各发 start+done，顺序正确"""
        events = []
        orch = _make_orchestrator(events)

        with patch(
            "src.services.agent.orchestrator.review",
            new_callable=AsyncMock,
            return_value=(FAKE_PLAN, ReviewResult(passed=True)),
        ):
            result = await orch.plan(PlanRequest(user_id=1, city="上海", days=5, budget=5000))

        assert result.plan == FAKE_PLAN
        assert _progress_of(events) == [
            ("research", "start"), ("research", "done"),
            ("plan", "start"), ("plan", "done"),
            ("review", "start"), ("review", "done"),
        ]

    @pytest.mark.asyncio
    async def test_review_retry_emits_second_round(self):
        """审校不过重跑：plan 出现第二轮 start（retry=True, attempt=2）"""
        events = []
        orch = _make_orchestrator(events)

        review_results = [
            (None, ReviewResult(passed=False, feedback="预算超了")),
            (FAKE_PLAN, ReviewResult(passed=True)),
        ]

        with patch(
            "src.services.agent.orchestrator.review",
            new_callable=AsyncMock,
            side_effect=review_results,
        ):
            await orch.plan(PlanRequest(user_id=1, city="上海", days=5, budget=5000))

        retry_starts = [
            e for e in events
            if e.get("type") == "progress"
            and e["data"]["stage"] == "plan"
            and e["data"]["status"] == "start"
            and e["data"].get("retry")
        ]
        assert len(retry_starts) == 1
        assert retry_starts[0]["data"]["attempt"] == 2

    @pytest.mark.asyncio
    async def test_no_on_event_no_crash(self):
        """on_event=None：正常执行不崩溃"""
        orch = Orchestrator(llm=MagicMock(), on_event=None)
        orch.research_agent = MagicMock()
        orch.research_agent.run = AsyncMock(return_value=AgentOutput(
            agent_name="research", result=ResearchBundle(),
        ))
        orch.planner_agent = MagicMock()
        orch.planner_agent.run = AsyncMock(return_value=AgentOutput(
            agent_name="planner", result="{}",
        ))

        with patch(
            "src.services.agent.orchestrator.review",
            new_callable=AsyncMock,
            return_value=(FAKE_PLAN, ReviewResult(passed=True)),
        ):
            result = await orch.plan(PlanRequest(user_id=1, city="上海", days=5, budget=5000))

        assert result.plan == FAKE_PLAN


class TestRecommendStreamProgress:

    @pytest.mark.asyncio
    async def test_stream_forwards_progress_and_tool_events(self):
        """_recommend_stream：progress/tool 事件透传且先于 complete；complete 含结果"""
        from src.controllers.trip_controller import _recommend_stream
        from src.schemas.trip import RecommendRequest

        async def fake_recommend(*, on_event=None, **kwargs):
            await on_event({"type": "progress", "data": {"stage": "research", "status": "start"}})
            await on_event({"type": "tool_start", "name": "retrieve_knowledge", "key": "attractions"})
            await on_event({"type": "tool_end", "name": "retrieve_knowledge", "key": "attractions"})
            await on_event({"type": "progress", "data": {"stage": "save", "status": "done"}})
            # complete 类型不应被透传（由 controller 统一发终态）
            await on_event({"type": "complete", "content": "raw"})
            return {"success": True, "data": {"id": 7}}

        body = RecommendRequest(city="上海", days=5, budget=5000)

        with patch("src.controllers.trip_controller.trip_service") as mock_svc:
            mock_svc.recommend = fake_recommend
            chunks = []
            async for chunk in _recommend_stream(body, user_id=1):
                chunks.append(chunk)

        payloads = [json.loads(c.removeprefix("data: ").strip()) for c in chunks]
        types = [p["type"] for p in payloads]

        assert types[0] == "start"
        assert "progress" in types
        assert "tool_start" in types
        assert "tool_end" in types
        # complete 只出现一次（Agent 内部 complete 被过滤）
        assert types.count("complete") == 1
        assert types.index("progress") < types.index("complete")

        complete = payloads[types.index("complete")]
        assert complete["data"]["data"]["id"] == 7

        # tool 事件带 key
        tool_start = payloads[types.index("tool_start")]
        assert tool_start["key"] == "attractions"

    @pytest.mark.asyncio
    async def test_stream_error_path(self):
        """recommend 抛错 → error 事件"""
        from src.controllers.trip_controller import _recommend_stream
        from src.schemas.trip import RecommendRequest

        async def fake_recommend(**kwargs):
            raise ValueError("行程推荐失败，请稍后重试")

        body = RecommendRequest(city="上海", days=5, budget=5000)

        with patch("src.controllers.trip_controller.trip_service") as mock_svc:
            mock_svc.recommend = fake_recommend
            chunks = []
            async for chunk in _recommend_stream(body, user_id=1):
                chunks.append(chunk)

        payloads = [json.loads(c.removeprefix("data: ").strip()) for c in chunks]
        assert payloads[-1]["type"] == "error"
