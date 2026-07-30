"""Orchestrator 编排层（纯代码，非 Agent）。

调度 ResearchAgent / PlannerAgent / review()，管理重试循环。
不含 LLM 调用，纯 asyncio 编排。

取代当前 planner_graph.py（LangGraph 图）。
"""

import copy
import json
import logging
import time
from typing import Optional, Callable, Awaitable

from langchain_openai import ChatOpenAI

from src.services.agent.agents.research_agent import ResearchAgent
from src.services.agent.agents.planner_agent import PlannerAgent
from src.services.agent.review import review
from src.services.agent.schemas import (
    PlanRequest,
    PlanResult,
    ResearchInput,
    ResearchBundle,
    PlannerInput,
    ReviewResult,
)
from src.services.agent.types import TokenUsage

logger = logging.getLogger(__name__)

# 最大重试轮次
MAX_REVIEW_RETRIES = 2


def _merge_usage(total: TokenUsage, delta: TokenUsage) -> TokenUsage:
    """合并 Token 用量。"""
    return {
        "prompt": total.get("prompt", 0) + delta.get("prompt", 0),
        "completion": total.get("completion", 0) + delta.get("completion", 0),
        "total": total.get("total", 0) + delta.get("total", 0),
        "cached": total.get("cached", 0) + delta.get("cached", 0),
    }


class Orchestrator:
    """多 Agent 编排器。

    职责：
    - 调度 ResearchAgent / PlannerAgent / review()
    - 管理重试循环（最多 MAX_REVIEW_RETRIES 轮）
    - 汇总 Token 用量
    - 不含 LLM 调用，纯 asyncio 编排
    """

    def __init__(
        self,
        llm: ChatOpenAI,
        fallback_llm: Optional[ChatOpenAI] = None,
        on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
    ):
        """初始化编排器。

        Args:
            llm: 主 LLM 实例（传给各 Agent）
            fallback_llm: 备用 LLM
            on_event: SSE 事件回调
        """
        self.research_agent = ResearchAgent(llm=llm, on_event=on_event)
        self.planner_agent = PlannerAgent(llm=llm, fallback_llm=fallback_llm)
        self.on_event = on_event

    async def _emit_progress(self, stage: str, status: str, **extra) -> None:
        """发送阶段进度事件（供前端展示实时步骤，best-effort）。"""
        if not self.on_event:
            return
        try:
            await self.on_event({
                "type": "progress",
                "data": {"stage": stage, "status": status, **extra},
            })
        except Exception:
            pass

    async def plan(self, request: PlanRequest) -> PlanResult:
        """全量规划流程。

        Phase 1: Research → Plan → Review（直线流程 + 重试循环）

        Args:
            request: 规划请求

        Returns:
            PlanResult 包含行程、审阅结果、Token 用量
        """
        _t0 = time.time()
        total_usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}

        # ── Phase 1: Research（Agent 自主搜索）──
        research_input = ResearchInput(
            city=request.city,
            days=request.days,
            budget=request.budget,
            interests=self._extract_interests(request.preferences),
            departure_city=request.departure_city,
            user_preferences=request.preferences,
        )

        await self._emit_progress("research", "start")
        research_output = await self.research_agent.run(research_input)
        if research_output.error:
            return PlanResult(
                error=f"Research 失败: {research_output.error}",
                duration_ms=int((time.time() - _t0) * 1000),
            )
        total_usage = _merge_usage(total_usage, research_output.usage)
        bundle: ResearchBundle = research_output.result
        await self._emit_progress(
            "research", "done",
            duration_ms=research_output.duration_ms,
            cached=research_output.duration_ms < 500,
        )

        # ── Phase 2: Plan（Agent 创造性生成）──
        planner_input = PlannerInput(
            bundle=bundle,
            city=request.city,
            days=request.days,
            budget=request.budget,
            preferences=request.preferences,
            departure_city=request.departure_city,
            message=request.message,
        )

        await self._emit_progress("plan", "start", attempt=1)
        planner_output = await self.planner_agent.run(planner_input)
        if planner_output.error:
            return PlanResult(
                error=f"Planner 失败: {planner_output.error}",
                usage=total_usage,
                duration_ms=int((time.time() - _t0) * 1000),
            )
        total_usage = _merge_usage(total_usage, planner_output.usage)
        raw_output: str = planner_output.result
        await self._emit_progress("plan", "done", attempt=1, duration_ms=planner_output.duration_ms)

        # ── Phase 3: Review + 重试循环 ──
        review_result: Optional[ReviewResult] = None
        parsed_plan: Optional[dict] = None

        for attempt in range(MAX_REVIEW_RETRIES + 1):
            await self._emit_progress("review", "start", attempt=attempt + 1)
            parsed_plan, review_result = await review(
                raw_output=raw_output,
                bundle=bundle,
                budget=request.budget,
                days=request.days,
            )

            if review_result.passed:
                await self._emit_progress("review", "done", attempt=attempt + 1, passed=True)
                break

            # 最后一轮不再重试
            if attempt >= MAX_REVIEW_RETRIES:
                logger.warning(
                    "orchestrator|review_failed_after_retries attempts=%d issues=%s",
                    attempt + 1, review_result.issues,
                )
                await self._emit_progress("review", "done", attempt=attempt + 1, passed=False)
                break

            # 带修改意见重跑 Planner
            logger.info(
                "orchestrator|retry attempt=%d feedback=%s",
                attempt + 1, review_result.feedback[:100],
            )
            planner_input.feedback = review_result.feedback
            await self._emit_progress("plan", "start", attempt=attempt + 2, retry=True)
            planner_output = await self.planner_agent.run(planner_input)
            if planner_output.error:
                break
            total_usage = _merge_usage(total_usage, planner_output.usage)
            raw_output = planner_output.result
            await self._emit_progress("plan", "done", attempt=attempt + 2, retry=True)

        duration_ms = int((time.time() - _t0) * 1000)
        logger.info(
            "orchestrator|plan_done city=%s days=%d duration=%dms passed=%s",
            request.city, request.days, duration_ms,
            review_result.passed if review_result else False,
        )

        return PlanResult(
            plan=parsed_plan,
            raw_output=raw_output,
            review=review_result,
            usage=total_usage,
            duration_ms=duration_ms,
        )

    async def modify(
        self,
        existing_trip: dict,
        modify_request: str,
        request: PlanRequest,
        target_days: Optional[list[int]] = None,
    ) -> PlanResult:
        """局部修改行程。

        支持两种模式：
        - 局部模式（target_days 有值）：只重生成指定天，其余天原样保留。
          通过 prompt 约束 Planner 只输出被修改的天，后端 merge 回原行程。
        - 全量模式（target_days=None）：走完整 modify 流程。

        Args:
            existing_trip: 已有行程 JSON
            modify_request: 修改要求自然语言
            request: 原始规划参数（city/days/budget）
            target_days: 要重新生成的天数列表（如 [2]），None 表示全量修改

        Returns:
            PlanResult 包含修改后的行程
        """
        _t0 = time.time()
        is_partial = target_days is not None and len(target_days) > 0
        total_usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}

        # ── Phase 1: Research ──
        await self._emit_progress("research", "start", mode="modify")
        research_input = ResearchInput(
            city=request.city,
            days=request.days,
            budget=request.budget,
            departure_city=request.departure_city,
            user_preferences=request.preferences,
            constraints=modify_request,
        )
        research_output = await self.research_agent.run(research_input)
        total_usage = _merge_usage(total_usage, research_output.usage)
        if research_output.error:
            return PlanResult(
                error=f"Research 失败: {research_output.error}",
                duration_ms=int((time.time() - _t0) * 1000),
            )
        bundle: ResearchBundle = research_output.result
        await self._emit_progress("research", "done", mode="modify", duration_ms=research_output.duration_ms)

        # ── Phase 2: Plan ──
        await self._emit_progress("plan", "start", mode="modify", attempt=1)
        planner_input = PlannerInput(
            bundle=bundle,
            city=request.city,
            days=request.days,
            budget=request.budget,
            preferences=request.preferences,
            departure_city=request.departure_city,
            feedback=f"用户修改要求：{modify_request}",
            existing_trip=existing_trip,
            target_days=target_days,
            message=modify_request,
        )

        planner_output = await self.planner_agent.run(planner_input)
        if planner_output.error:
            return PlanResult(error=planner_output.error, duration_ms=int((time.time() - _t0) * 1000))
        total_usage = _merge_usage(total_usage, planner_output.usage)
        await self._emit_progress("plan", "done", mode="modify", attempt=1, duration_ms=planner_output.duration_ms)

        # ── Phase 3: Review ──
        await self._emit_progress("review", "start", mode="modify")
        raw_to_review = planner_output.result
        if is_partial:
            # 局部模式：先解析 planner 输出，merge 回原行程，再送审
            partial_parsed = self._parse_json_safe(planner_output.result)
            if partial_parsed:
                merged = await self._merge_partial_plan(existing_trip, partial_parsed, target_days)
                raw_to_review = json.dumps(merged, ensure_ascii=False)
        parsed_plan, review_result = await review(
            raw_output=raw_to_review,
            bundle=bundle,
            budget=request.budget,
            days=request.days,
            target_days=target_days,
        )
        await self._emit_progress("review", "done", mode="modify", passed=review_result.passed)

        duration_ms = int((time.time() - _t0) * 1000)
        if parsed_plan is None:
            # review 解析失败但 Planner 未报错：补一个明确错误，避免上层显示"未知错误"
            issues = review_result.issues if review_result else ["行程解析失败"]
            return PlanResult(
                error=f"修改方案无效：{'; '.join(issues)}",
                raw_output=planner_output.result,
                review=review_result,
                usage=total_usage,
                duration_ms=duration_ms,
            )
        return PlanResult(
            plan=parsed_plan,
            raw_output=planner_output.result,
            review=review_result,
            usage=total_usage,
            duration_ms=duration_ms,
        )

    async def _merge_partial_plan(
        self,
        existing_trip: dict,
        partial_plan: dict,
        target_days: list[int],
    ) -> dict:
        """将 Planner 局部输出的天 merge 回原行程。

        Args:
            existing_trip: 原行程 dict
            partial_plan: Planner 输出的部分行程（只含被修改的天）
            target_days: 被修改的天数列表

        Returns:
            merge 后的完整行程 dict
        """
        merged = copy.deepcopy(existing_trip)
        new_itinerary = partial_plan.get("dailyItinerary", [])
        old_itinerary = merged.get("dailyItinerary", [])
        target_set = set(target_days)

        # 只使用 target_days 中的天（过滤 planner 多余输出）
        new_by_day = {d.get("day"): d for d in new_itinerary if d.get("day") in target_set}

        # 替换被修改的天
        for i, day_entry in enumerate(old_itinerary):
            day_num = day_entry.get("day")
            if day_num in new_by_day:
                old_itinerary[i] = new_by_day[day_num]

        # 如果原行程没有的天追加
        existing_days = {d.get("day") for d in old_itinerary if d.get("day")}
        for day_num in sorted(target_set):
            if day_num in new_by_day and day_num not in existing_days:
                old_itinerary.append(new_by_day[day_num])

        merged["dailyItinerary"] = old_itinerary

        # 增量重算预算：保留未被修改天的原值，加上新天的值
        new_bd = partial_plan.get("budgetBreakdown")
        if new_bd:
            old_bd = merged.get("budgetBreakdown", {})
            merged["budgetBreakdown"] = {
                k: new_bd.get(k, old_bd.get(k, 0))
                for k in ("accommodation", "food", "transportation", "tickets", "other")
            }
            merged["totalBudget"] = sum(merged["budgetBreakdown"].values())

        return merged

    @staticmethod
    def _parse_json_safe(raw: str) -> Optional[dict]:
        """安全解析 JSON（含修复）。"""
        if not raw or not raw.strip():
            return None
        try:
            return json.loads(raw)
        except Exception:
            pass
        try:
            from src.services.agent.nodes.validate import repair_json
            return json.loads(repair_json(raw))
        except Exception:
            return None

    @staticmethod
    def _extract_interests(preferences: Optional[dict]) -> list[str]:
        """从用户偏好中提取兴趣标签。"""
        if not preferences:
            return []
        interests = preferences.get("interests", [])
        if isinstance(interests, list):
            return interests
        return []
