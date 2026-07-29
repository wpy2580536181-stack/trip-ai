"""ChatAgent 模块（对话前台）。

单 Agent ReAct 模式：LLM 自主决定是否调工具、调哪个。
- 普通问答：直接流式返回（低延迟）
- 规划请求：通过 tool_call trigger_plan 升级为 Orchestrator
- 修改请求：通过 tool_call trigger_modify 升级为 Orchestrator.modify

取代当前 chat_graph.py + nodes/legacy_agent.py + nodes/chat_planner.py。
"""

import logging
import time
from typing import Optional, Callable, Awaitable, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.services.agent.agents.base_agent import BaseAgent, AgentOutput
from src.services.agent.types import TokenUsage

logger = logging.getLogger(__name__)


def _merge_usage(total: dict, delta: dict) -> dict:
    """合并 Token 用量（四键相加）。"""
    return {
        k: (total or {}).get(k, 0) + (delta or {}).get(k, 0)
        for k in ("prompt", "completion", "total", "cached")
    }


class ChatAgent(BaseAgent):
    """Chat Agent：对话前台，单 Agent + 工具，ReAct 模式。

    核心设计：
    - 持有多轮 conversation_history
    - LLM 自主决定是否调工具（RAG/酒店/天气）
    - 通过 trigger_plan / trigger_modify 工具"升级"到 Orchestrator
    - trip_context 注入（用户已有行程摘要）
    """

    name = "chat"

    def __init__(
        self,
        llm: ChatOpenAI,
        on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
        system_prompt: str = "",
        user_id: int = 0,
    ):
        """初始化 ChatAgent。

        Args:
            llm: LLM 实例（streaming=True）
            on_event: SSE 事件回调
            system_prompt: 系统提示词（由 agent_engine 构建）
            user_id: 当前用户 ID（供 trigger_plan 落库使用，0 表示未知）
        """
        # 工具在 run() 时动态绑定（因为需要延迟加载）
        super().__init__(llm=llm, tools=[], system_prompt=system_prompt)
        self.on_event = on_event
        self._user_id = user_id

    async def run(
        self,
        message: str,
        conversation_history: Optional[list] = None,
        system_prompt: Optional[str] = None,
        trip_context: Optional[str] = None,
        trip_meta: Optional[dict] = None,
        user_id: int = 0,
    ) -> AgentOutput:
        """执行对话。

        Args:
            message: 用户当前消息
            conversation_history: 多轮对话历史（LangChain 消息列表）
            system_prompt: 系统提示词（覆盖初始化时的）
            trip_context: 用户已有行程摘要（注入 system prompt）
            trip_meta: 行程元数据（trip_id/user_id/city/days/budget/content，供 modify 使用）
            user_id: 当前用户 ID（供 trigger_plan 落库使用，0 表示未知）

        Returns:
            AgentOutput，result 为回复文本
        """
        _t0 = time.time()
        self._trip_meta = trip_meta
        self._user_id = user_id

        # 构建 system prompt
        sys_prompt = system_prompt or self.system_prompt
        if trip_context:
            sys_prompt += f"\n\n# 用户当前行程\n{trip_context}\n"
            sys_prompt += (
                "\n# 行中伴随能力\n"
                "你当前具备以下行中服务能力：\n"
                "- 周边搜索：用户问“附近/周边/XXX旁边”时，用 search_nearby_commute_pois_tool 搜索\n"
                "- 通勤规划：用户问“怎么去/最快/最近”时，用 compute_optimal_commute_tool 规划\n"
                "- 地点定位：用户只给地名没给坐标时，先用 search_commute_tips_tool 获取坐标\n"
                "- 位置感知：当用户告知当前位置时，结合行程进度判断：\n"
                "  - 如果接近用餐时段（11:00-13:00 / 17:00-19:00），主动推荐附近餐厅\n"
                "  - 计算到下一站点的通勤方案\n"
                "  - 如果用户偏离计划路线，提醒并给出建议\n"
                "行程中各景点坐标已在上方列出，可直接使用。\n"
            )

        # 构建消息列表
        messages = [{"role": "system", "content": sys_prompt}]

        # 注入对话历史
        if conversation_history:
            for msg in conversation_history:
                if hasattr(msg, "content"):
                    role = "human" if isinstance(msg, HumanMessage) else "ai"
                    messages.append({"role": role, "content": msg.content})
                elif isinstance(msg, dict):
                    messages.append(msg)

        # 当前用户消息
        messages.append({"role": "human", "content": message})

        # 获取工具（延迟加载）
        tools = await self._get_tools()

        # 流式调用 LLM（带工具绑定）
        self.tools = tools
        try:
            content, usage, raw_msg = await self._stream_llm(
                messages=messages,
                timeout_s=60.0,
            )
        except Exception as e:
            return AgentOutput(
                agent_name=self.name,
                error=str(e),
                duration_ms=int((time.time() - _t0) * 1000),
            )

        # 检查是否有 tool_calls（trigger_plan / trigger_modify）
        tool_calls = getattr(raw_msg, "tool_calls", None)
        if tool_calls:
            for tc in tool_calls:
                tc_name = tc.get("name", "")
                tc_args = tc.get("args", {})
                logger.info("chat_agent|tool_call name=%s args=%s", tc_name, tc_args)

                if tc_name == "trigger_plan":
                    # 升级为 Orchestrator.plan()
                    plan_result, plan_usage = await self._escalate_plan(tc_args)
                    if plan_result:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=plan_result,
                            usage=_merge_usage(usage, plan_usage),
                            duration_ms=duration_ms,
                        )

                elif tc_name == "trigger_modify":
                    # 升级为 Orchestrator.modify()
                    modify_result, modify_usage = await self._escalate_modify(tc_args)
                    if modify_result:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=modify_result,
                            usage=_merge_usage(usage, modify_usage),
                            duration_ms=duration_ms,
                        )

                elif tc_name == "trigger_patch":
                    # Slot 级精确修改（不走 Planner）
                    patch_result, patch_usage = await self._escalate_patch(tc_args)
                    if patch_result:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=patch_result,
                            usage=_merge_usage(usage, patch_usage),
                            duration_ms=duration_ms,
                        )

                elif tc_name == "select_skill":
                    # 技能激活：L1→L2→L3 渐进式执行（对齐 Anthropic 规范）
                    skill_result = await self._run_selected_skill(raw_msg, message)
                    if skill_result is not None:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=skill_result.content,
                            usage=usage,
                            duration_ms=duration_ms,
                        )

        # 流式发送已在 _stream_llm 中完成，此处不再重复发送

        duration_ms = int((time.time() - _t0) * 1000)
        return AgentOutput(
            agent_name=self.name,
            result=content,
            usage=usage,
            duration_ms=duration_ms,
        )

    async def _stream_llm(
        self,
        messages: list[dict],
        timeout_s: float = 60.0,
    ) -> tuple[str, dict, any]:
        """流式调用 LLM，通过 on_event 逐 token 推送。

        Returns:
            (full_content, usage, raw_message) 元组
        """
        import asyncio
        from langchain_core.messages import AIMessage, AIMessageChunk

        llm = self.llm
        if self.tools:
            llm = llm.bind_tools(self.tools)

        full_content = ""
        usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
        raw_msg = None

        _t0 = time.time()
        try:
            async def _do_stream():
                nonlocal full_content, usage, raw_msg
                async for chunk in llm.astream(messages):
                    # 提取文本内容
                    if isinstance(chunk, AIMessageChunk):
                        token = chunk.content if isinstance(chunk.content, str) else ""
                        if token:
                            full_content += token
                            # 流式推送给前端
                            if self.on_event:
                                await self.on_event({"type": "chunk", "content": token})
                        # 累积 tool_calls
                        if raw_msg is None:
                            raw_msg = chunk
                        else:
                            raw_msg = raw_msg + chunk
                    else:
                        full_content += str(chunk)

                # 提取 usage
                if raw_msg and isinstance(raw_msg, AIMessage):
                    um = getattr(raw_msg, "usage_metadata", None)
                    if um:
                        usage["prompt"] = um.get("input_tokens", 0)
                        usage["completion"] = um.get("output_tokens", 0)
                        usage["total"] = um.get("total_tokens", 0)

            await asyncio.wait_for(_do_stream(), timeout=timeout_s)

        except asyncio.TimeoutError:
            raise TimeoutError(f"{self.name} LLM 流式调用超时（{timeout_s}秒）")

        logger.info(
            "%s|stream duration=%dms content_len=%d",
            self.name, int((time.time() - _t0) * 1000), len(full_content),
        )

        return full_content, usage, raw_msg

    async def _get_tools(self) -> list:
        """获取 ChatAgent 的工具列表（延迟加载）。

        工具列表：
        - retrieve_knowledge（RAG 检索）
        - search_hotels（酒店搜索）
        - trigger_plan（升级：触发全量规划）
        - trigger_modify（升级：触发局部修改）
        - search_nearby_commute_pois（周边 POI 搜索）
        - search_commute_tips（地名→坐标）
        - compute_optimal_commute（通勤择优）
        - amap_weather（MCP 天气，如果可用）
        """
        from src.services.agent.tools import retrieve_knowledge_tool, search_hotels_tool
        from src.services.agent.tools.commute import (
            compute_optimal_commute_tool,
            search_commute_tips_tool,
            search_nearby_commute_pois_tool,
        )
        from src.services.agent.agents.trigger_tools import trigger_plan, trigger_modify, trigger_patch
        from src.services.agent.skills import select_skill

        tools = [
            retrieve_knowledge_tool,
            search_hotels_tool,
            trigger_plan,
            trigger_modify,
            trigger_patch,
            select_skill,
            search_nearby_commute_pois_tool,
            search_commute_tips_tool,
            compute_optimal_commute_tool,
        ]

        # 尝试加载高德 MCP 天气工具
        try:
            from src.services.mcp.amap_client import get_amap_tools
            amap_tools = await get_amap_tools()
            if amap_tools:
                tools.extend(amap_tools[:3])
        except Exception:
            pass

        return tools

    async def _run_selected_skill(
        self, response: Any, message: str
    ) -> Optional[Any]:
        """检测 select_skill 工具调用并执行对应的技能（L1→L2→L3 渐进式披露）。

        复用语基的 SkillRegistry（与 AgentEngine 共享单例），把整篇 SKILL.md 交给
        LLM 借助底层工具自行编排。meituan-travel 这类 CLI 型技能需要 shell 能力，
        故在此注入沙箱化的 meituan_query_tool。

        Returns:
            SkillResult（命中并执行）或 None（未选中技能 / 未注册）
        """
        from src.services.agent.skills import get_skill_registry, load_builtin_skills
        from src.services.agent.skills.selector_tool import extract_select_skill_call
        from src.services.agent.skills.types import SkillContext
        from src.services.agent.tools import (
            retrieve_knowledge_tool,
            search_hotels_tool,
            calculate_distance_tool,
            compute_optimal_commute_tool,
            search_commute_tips_tool,
            search_nearby_commute_pois_tool,
        )

        skill_name = extract_select_skill_call(response)
        if not skill_name:
            return None

        registry = get_skill_registry()
        load_builtin_skills(registry)  # 幂等，确保技能已加载（不依赖 AgentEngine 先构造）
        if registry.get(skill_name) is None:
            logger.warning("chat_agent|skill %s 未注册，跳过", skill_name)
            return None

        tools = [
            retrieve_knowledge_tool,
            search_hotels_tool,
            calculate_distance_tool,
            compute_optimal_commute_tool,
            search_commute_tips_tool,
            search_nearby_commute_pois_tool,
        ]
        # 美团 CLI 工具（环境具备则注入，供 meituan-travel 技能执行）
        try:
            from src.services.agent.tools.meituan import meituan_query_tool
            tools.append(meituan_query_tool)
        except Exception:  # noqa: BLE001
            pass

        ctx = SkillContext(
            llm=self.llm,
            tools=tools,
            registry=registry,
            user_input=message,
        )
        logger.info("chat_agent|run_skill name=%s", skill_name)
        return await registry.execute(skill_name, ctx)

    @staticmethod
    def _build_trip_diff(old: dict, new: dict) -> list[dict]:
        """比较新旧行程，生成 Slot 级变更列表。"""
        changes = []
        old_days = {d.get("day"): d for d in (old.get("dailyItinerary") or []) if d.get("day")}
        new_days = {d.get("day"): d for d in (new.get("dailyItinerary") or []) if d.get("day")}
        all_days = sorted(set(old_days) | set(new_days))
        for day_num in all_days:
            old_day = old_days.get(day_num, {})
            new_day = new_days.get(day_num, {})
            for period in ("morning", "afternoon", "evening"):
                old_spot = (old_day.get(period) or {}).get("spot", "")
                new_spot = (new_day.get(period) or {}).get("spot", "")
                if old_spot != new_spot:
                    changes.append({
                        "day": day_num,
                        "period": period,
                        "oldSpot": old_spot or "(无)",
                        "newSpot": new_spot or "(无)",
                    })
        return changes

    async def _escalate_plan(self, args: dict) -> tuple[Optional[str], dict]:
        """升级为 Orchestrator.plan()，规划结果持久化为 Trip（与 modify 路径对称）。

        成功落库时通过 on_event 发出 trip_planned 事件（前端展示详情入口）。
        返回 (回复文本, 升级路径 usage)。
        """
        try:
            from src.services.agent.orchestrator import Orchestrator
            from src.services.agent.schemas import PlanRequest
            from src.services.trip_service import TripService

            user_id = getattr(self, "_user_id", 0)
            # 兜底：对话级 user_id 缺失时，从关联行程取（与 _escalate_modify 一致），
            # 避免偏好加载与落库按 user_id=0 走而丢失身份。
            if user_id <= 0:
                meta = getattr(self, "_trip_meta", None)
                if meta and meta.get("user_id"):
                    user_id = meta["user_id"]
            city = args.get("city", "")
            days = args.get("days", 3)
            budget = args.get("budget", 5000)
            departure_city = args.get("departure_city") or None

            orchestrator = Orchestrator(llm=self.llm, on_event=self.on_event)
            request = PlanRequest(
                user_id=user_id,
                city=city,
                days=days,
                budget=budget,
                departure_city=departure_city,
                message=f"规划{city}{days}日游",
            )
            result = await orchestrator.plan(request)
            if result.plan:
                if user_id > 0:
                    # 落库为新 Trip（无父版本），发结构化事件供前端展示入口
                    new_trip_id = await TripService._persist_trip(
                        user_id=user_id,
                        from_city=departure_city,
                        parsed=result.plan,
                        budget=budget,
                        parent_trip_id=None,
                    )
                    summary = (
                        f"已为您规划 {result.plan.get('city', city)}"
                        f"{result.plan.get('days', days)}日游（预算{budget}元），"
                        f"行程已保存，可在行程详情页查看。"
                    )
                    if self.on_event:
                        await self.on_event({
                            "type": "trip_planned",
                            "data": {
                                "newTripId": new_trip_id,
                                "summary": summary,
                            },
                        })
                    return summary, result.usage
                # 防御：无有效 user_id 时不落库，仅返回文本摘要
                import json
                return json.dumps(result.plan, ensure_ascii=False), result.usage
            return result.raw_output, result.usage
        except Exception as e:
            logger.error("chat_agent|escalate_plan failed: %s", e)
            return None, {}

    async def _escalate_modify(self, args: dict) -> tuple[Optional[str], dict]:
        """升级为 Orchestrator.modify()，生成修改版行程并持久化为 v2 Trip。

        成功时通过 on_event 发出结构化 trip_modified 事件（前端据此刷新行程）。
        返回 (人类可读的摘要文本, 升级路径 usage)，文本作为 assistant 消息落库。
        """
        meta = getattr(self, "_trip_meta", None)
        if not meta:
            return "当前没有关联行程，无法修改。请先在行程详情页打开对话。", {}

        try:
            from src.services.agent.orchestrator import Orchestrator
            from src.services.agent.schemas import PlanRequest
            from src.services.trip_service import TripService

            orchestrator = Orchestrator(llm=self.llm, on_event=self.on_event)
            request = PlanRequest(
                user_id=meta["user_id"],
                city=meta["city"],
                days=meta["days"],
                budget=meta["budget"],
                departure_city=meta.get("departure_city"),
            )
            target_days_str = args.get("target_days", "") or ""
            target_days = None
            if target_days_str.strip():
                try:
                    target_days = [int(d.strip()) for d in target_days_str.split(",") if d.strip().isdigit()]
                except Exception:
                    pass

            result = await orchestrator.modify(
                existing_trip=meta["content"],
                modify_request=args.get("modify_request", ""),
                request=request,
                target_days=target_days,
            )
            if result.plan:
                new_trip_id = await TripService._persist_trip(
                    user_id=meta["user_id"],
                    from_city=meta.get("departure_city"),
                    parsed=result.plan,
                    budget=meta["budget"],
                    parent_trip_id=meta["trip_id"],
                    status="candidate",
                )
                if self.on_event:
                    diff = self._build_trip_diff(meta["content"], result.plan)
                    await self.on_event({
                        "type": "trip_diff",
                        "data": {
                            "newTripId": new_trip_id,
                            "parentTripId": meta["trip_id"],
                            "changes": diff,
                        },
                    })
                summary = f"已为您生成修改方案，请确认后生效。"
                return summary, result.usage
            return f"修改失败：{result.error or '未知错误'}", result.usage
        except Exception as e:
            logger.error("chat_agent|escalate_modify failed: %s", e)
            return f"行程修改失败：{e}", {}

    async def _escalate_patch(self, args: dict) -> tuple[Optional[str], dict]:
        """Slot 级精确修改（不走 LLM，直接 Patch 行程 JSON）。

        Patch 失败时自动降级为 _escalate_modify（全量 modify）。
        """
        meta = getattr(self, "_trip_meta", None)
        if not meta:
            return "当前没有关联行程，无法修改。", {}

        op = args.get("op", "")
        day = args.get("day", 0)
        period = args.get("period", "")
        spot_name = args.get("spot_name", "")
        description = args.get("description", "")
        period_b = args.get("period_b", "")

        try:
            from src.services.agent.patch_engine import apply_patch, PatchError
            from src.services.trip_service import TripService

            patched = apply_patch(
                trip=meta["content"],
                op=op,
                day=day,
                period=period,
                spot_name=spot_name,
                description=description,
                period_b=period_b,
            )

            new_trip_id = await TripService._persist_trip(
                user_id=meta["user_id"],
                from_city=meta.get("departure_city"),
                parsed=patched,
                budget=meta["budget"],
                parent_trip_id=meta["trip_id"],
                status="candidate",
            )

            if self.on_event:
                diff = self._build_trip_diff(meta["content"], patched)
                await self.on_event({
                    "type": "trip_diff",
                    "data": {
                        "newTripId": new_trip_id,
                        "parentTripId": meta["trip_id"],
                        "changes": diff,
                    },
                })
            return "已为您生成修改方案，请确认后生效。", {"prompt": 0, "completion": 0, "total": 0, "cached": 0}

        except PatchError as e:
            logger.info("chat_agent|patch_failed, falling back to modify: %s", e)
            modify_args = {
                "modify_request": args.get("modify_request", f"第{day}天{period}更换为{spot_name}"),
                "target_days": str(day),
            }
            return await self._escalate_modify(modify_args)
        except Exception as e:
            logger.error("chat_agent|escalate_patch failed: %s", e)
            modify_args = {
                "modify_request": args.get("modify_request", f"第{day}天{period}更换为{spot_name}"),
                "target_days": str(day),
            }
            return await self._escalate_modify(modify_args)
