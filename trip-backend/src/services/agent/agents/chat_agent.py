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
        self.tools = tools

        # 预检测意图：在调用 LLM 前直接执行附近/通勤工具（保证 card 事件触发）
        pre_tool_result = await self._try_pre_llm_tool(message)
        if pre_tool_result:
            # 工具已执行并发了 card，把结果注入 LLM 上下文
            sys_prompt += f"\n\n# 工具查询结果\n{pre_tool_result}\n"
            messages[0] = {"role": "system", "content": sys_prompt}

        # 流式调用 LLM（带工具绑定）
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

                else:
                    # 非 trigger 工具：执行并发送 card 事件
                    card_result = await self._execute_tool_card(tc_name, tc_args, message)
                    if card_result is not None:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=card_result,
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

    async def _try_pre_llm_tool(self, user_msg: str) -> Optional[str]:
        """LLM 调用前预检测意图，直接执行工具并发送 card 事件。

        不依赖 LLM 主动调工具，直接调高德 API 获取数据并发 card。
        保证 card 事件稳定触发。
        """
        logger.info("chat_agent|pre_llm_check msg=%s", user_msg[:50])
        nearby_kw = {"附近", "周边", "周围", "旁边"}
        commute_kw = {"怎么走", "怎么去", "通勤", "路线", "过去", "坐车", "打车", "最快"}
        food_kw = {"好吃的", "餐厅", "美食", "吃", "饭"}
        spot_kw = {"好玩的", "景点", "玩", "逛"}

        is_nearby = any(kw in user_msg for kw in nearby_kw)
        is_commute = any(kw in user_msg for kw in commute_kw)
        is_food = any(kw in user_msg for kw in food_kw)
        is_spot = any(kw in user_msg for kw in spot_kw)

        if not is_nearby and not is_commute:
            logger.info("chat_agent|pre_llm_no_match")
            return None

        logger.info("chat_agent|pre_llm_match nearby=%s commute=%s food=%s spot=%s",
                     is_nearby, is_commute, is_food, is_spot)

        import json as _json

        # 直调高德 API（绕过 resilience/tool_cache 包装，避免 fallback）
        from src.services.commute_service import search_input_tips, search_nearby_pois

        import re as _re
        kw = _re.sub(r"(附近|周边|周围|有什么|好吃的|好玩的|景点|推荐|餐厅|美食|吃|玩|逛|的)", "", user_msg).strip()
        if not kw:
            kw = user_msg[:10]

        logger.info("chat_agent|pre_llm_search kw=%s", kw)
        try:
            tips = await search_input_tips(kw, None, 3)
        except Exception as e:
            logger.warning("chat_agent|pre_llm_tips_failed kw=%s err=%s", kw, e)
            return None

        if not tips or not isinstance(tips, list) or len(tips) == 0:
            logger.info("chat_agent|pre_llm_tips_empty")
            return None

        first = tips[0]
        lat = first.get("lat") or first.get("latitude")
        lng = first.get("lng") or first.get("longitude")
        logger.info("chat_agent|pre_llm_got_coord name=%s lat=%s lng=%s", first.get("name"), lat, lng)
        if lat is None or lng is None:
            return None

        city = first.get("city", "")

        if is_commute:
            try:
                from src.services.commute_service import compute_optimal_commute
                commute_result = await compute_optimal_commute(
                    origin={"name": first.get("name"), "lat": lat, "lng": lng, "city": city},
                    destinations=[{"name": "目的地", "city": city}],
                    mode="walking",
                    city=city,
                    compare_modes=True,
                )
                await self._emit_commute_card(commute_result, {}, user_msg)
                return "已查询通勤方案，路线信息如上。"
            except Exception as e:
                logger.warning("chat_agent|pre_llm_commute_failed err=%s", e)

        if is_nearby:
            try:
                nearby_kw = "餐饮" if is_food else ("景点" if is_spot else None)
                pois = await search_nearby_pois(lat, lng, 1000, nearby_kw, 10)
                logger.info("chat_agent|pre_llm_poi_result count=%d", len(pois) if pois else 0)
                await self._emit_poi_card(pois, {}, user_msg)
                return "已查询附近结果如上。"
            except Exception as e:
                logger.warning("chat_agent|pre_llm_nearby_failed err=%s", e)

        return None

    async def _execute_tool_card(self, tool_name: str, args: dict, user_msg: str) -> Optional[str]:
        """执行普通工具并发送 card 事件。

        支持自动串联：search_commute_tips_tool → search_nearby_commute_pois_tool → poi_list 卡片
        单步：search_nearby_commute_pois_tool → poi_list 卡片
             compute_optimal_commute_tool → commute_compare 卡片
        """
        tool_fn = None
        for t in getattr(self, "tools", []) or []:
            if getattr(t, "name", "") == tool_name:
                tool_fn = t
                break

        if not tool_fn:
            return None

        try:
            import json as _json

            if tool_name == "search_commute_tips_tool":
                # 用户先查坐标（地名→lat/lng），判断是否接着查周边
                result_str = await tool_fn.ainvoke(args)
                tips = _json.loads(result_str) if isinstance(result_str, str) else result_str
                if not tips or isinstance(tips, dict) and tips.get("error"):
                    return None
                first = tips[0] if isinstance(tips, list) else tips
                lat = first.get("lat") or first.get("latitude")
                lng = first.get("lng") or first.get("longitude")
                if lat is not None and lng is not None and self._is_nearby_query(user_msg):
                    return await self._auto_poi_search(lat, lng, user_msg)
                return None

            result_str = await tool_fn.ainvoke(args)
            data = _json.loads(result_str) if isinstance(result_str, str) else result_str

            if tool_name == "search_nearby_commute_pois_tool":
                return await self._emit_poi_card(data, args, user_msg)
            elif tool_name == "compute_optimal_commute_tool":
                return await self._emit_commute_card(data, args, user_msg)
        except Exception as e:
            logger.warning("chat_agent|tool_card_failed name=%s err=%s", tool_name, e)

        return None

    @staticmethod
    def _is_nearby_query(user_msg: str) -> bool:
        """判断用户消息是否在问周边/附近。"""
        nearby_kw = {"附近", "周边", "周围", "旁边的", "有什么好吃的", "有什么好玩的",
                     "推荐", "餐厅", "美食", "景点", "吃", "玩", "逛"}
        return any(kw in user_msg for kw in nearby_kw)

    async def _auto_poi_search(self, lat: float, lng: float, user_msg: str) -> Optional[str]:
        """获取坐标后自动查周边 POI 并发送 card 事件。"""
        keywords = None
        if any(kw in user_msg for kw in ("好吃的", "餐厅", "美食", "吃", "饭")):
            keywords = "餐饮"
        elif any(kw in user_msg for kw in ("好玩的", "景点", "玩", "逛")):
            keywords = "景点"

        poi_fn = None
        for t in getattr(self, "tools", []) or []:
            if getattr(t, "name", "") == "search_nearby_commute_pois_tool":
                poi_fn = t
                break

        if not poi_fn:
            return None

        try:
            import json as _json
            poi_args = {"lat": float(lat), "lng": float(lng), "radius": 1000, "limit": 10}
            if keywords:
                poi_args["keywords"] = keywords
            result_str = await poi_fn.ainvoke(poi_args)
            data = _json.loads(result_str) if isinstance(result_str, str) else result_str
            return await self._emit_poi_card(data, poi_args, user_msg)
        except Exception as e:
            logger.warning("chat_agent|auto_poi_failed err=%s", e)
            return None

    async def _emit_poi_card(self, data: dict, args: dict, user_msg: str) -> str:
        """POI 工具结果 → poi_list card 事件 + 文本摘要。"""
        items = data if isinstance(data, list) else data.get("data") or data.get("pois") or []
        if not items and isinstance(data, dict):
            items = [data]

        card_items = []
        for it in items[:10]:
            card_items.append({
                "name": it.get("name", ""),
                "distance": it.get("distance", ""),
                "rating": it.get("rating"),
                "cost": it.get("cost", ""),
            })

        if self.on_event and card_items:
            await self.on_event({
                "type": "card",
                "card_type": "poi_list",
                "data": {
                    "items": card_items,
                },
            })

        count = len(card_items)
        kw = args.get("keywords", "") or ""
        return f"附近找到 {count} 个{'相关' if kw else ''}地点。" if count else "附近暂未找到相关地点。"

    async def _emit_commute_card(self, data: dict, args: dict, user_msg: str) -> str:
        """通勤工具结果 → commute_compare card 事件 + 文本摘要。"""
        import json as _json

        recommended = data.get("recommended")
        candidates = data.get("candidates") or []

        if self.on_event:
            options = []
            for c in (candidates or []):
                mode_label = {"walking": "步行", "transit": "公交", "driving": "驾车", "cycling": "骑行"}.get(
                    (c.get("per_mode") or [{}])[0].get("mode") if c.get("per_mode") else "", ""
                ) or c.get("name", "")
                options.append({
                    "mode": mode_label,
                    "duration": c.get("duration_text") or f"{c.get('duration_sec', 0)//60}分钟",
                    "distance": c.get("distance_text") or f"{c.get('distance_m', 0)/1000:.1f}km",
                })

            await self.on_event({
                "type": "card",
                "card_type": "commute_compare",
                "data": {
                    "options": options[:5],
                    "recommended": 0,
                },
            })

        rec = recommended or (candidates[0] if candidates else None)
        if rec:
            sec = rec.get("duration_sec", 0)
            return f"最优方案约 {sec//60} 分钟。"
        return "通勤方案计算失败。"

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
