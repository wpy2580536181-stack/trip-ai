"""ResearchAgent 模块。

真 Agent：LLM 自主决定搜索策略（搜什么、搜几次、结果够不够）。
Phase 1 先移植当前 research_node 的固定并行逻辑，后续升级为 LLM 决策。

工具列表：
- retrieve_knowledge（RAG 检索）
- search_hotels（酒店搜索）
- amap_weather（MCP 天气）
- calculate_distance（距离计算）
"""

import asyncio
import logging
import re
import time
from typing import Optional, Callable, Awaitable, Any

from langchain_openai import ChatOpenAI

from src.services.agent.agents.base_agent import BaseAgent, AgentInput, AgentOutput
from src.services.agent.schemas import ResearchInput, ResearchBundle, SpotItem
from src.services.agent.types import TokenUsage

logger = logging.getLogger(__name__)

# 工具调用失败时的降级消息
HOTEL_FALLBACK = "住宿信息暂时不可用，请基于通用旅行知识回答。"
DISTANCE_FALLBACK = "距离计算暂时不可用。"
WEATHER_FALLBACK = "天气服务暂时不可用，请根据季节常识判断。"
ATTRACTION_FALLBACK = "景点信息暂时不可用，请基于通用旅行知识回答。"
FOOD_FALLBACK = "美食信息暂时不可用，请基于通用旅行知识回答。"


class ResearchAgent(BaseAgent):
    """Research Agent：并行调用工具获取候选池数据。

    Phase 1：固定并行 5 个工具调用（移植自 research_node）。
    Phase 5：当有 constraints 时，LLM 动态决定搜索 query。
    """

    name = "research"

    def __init__(
        self,
        llm: ChatOpenAI,
        on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
    ):
        """初始化 ResearchAgent。

        Args:
            llm: LLM 实例（用于动态 query 生成）
            on_event: SSE 事件回调（tool_start / tool_end）
        """
        super().__init__(llm=llm, tools=[], system_prompt="")
        self.on_event = on_event

    @staticmethod
    def _extract_spot_items(text: str, category: str, max_items: int = 10) -> list[SpotItem]:
        """从格式化文本中提取景点/美食名称。

        format_search_results 格式：
          1. 景点名称（城市）
             - 评分：X 分
             - 介绍：...

        Args:
            text: 格式化文本
            category: 分类（"attraction" 或 "food"）
            max_items: 最多提取数量

        Returns:
            SpotItem 列表
        """
        items = []
        # 匹配 "数字. 名称（城市）" 格式
        pattern = re.compile(r'^\s*\d+\.\s+(.+?)(?:（|\().+?(?:）|\))', re.MULTILINE)
        for match in pattern.finditer(text):
            name = match.group(1).strip()
            if name and len(name) < 30:  # 过滤过长名称
                items.append(SpotItem(name=name, category=category))
                if len(items) >= max_items:
                    break
        return items

    async def run(self, input: ResearchInput) -> AgentOutput:
        """执行搜索：并行调用 RAG / 酒店 / 天气 / 距离工具。

        Args:
            input: ResearchInput 包含城市、天数、预算、兴趣等

        Returns:
            AgentOutput，result 为 ResearchBundle
        """
        _t0 = time.time()

        # 缓存检查
        from src.services.agent.research_bundle_cache import get_bundle_cache
        bundle_cache = get_bundle_cache()
        cached = await bundle_cache.get(
            input.city, input.budget, input.days,
            input.departure_city, input.user_preferences,
        )
        if cached is not None:
            logger.info("research_agent|cache_hit city=%s days=%d", input.city, input.days)
            bundle = ResearchBundle(
                attractions=cached.get("attractions"),
                food=cached.get("food"),
                hotels=cached.get("hotels"),
                weather=cached.get("weather"),
                distance=cached.get("distance"),
            )
            return AgentOutput(
                agent_name=self.name,
                result=bundle,
                duration_ms=int((time.time() - _t0) * 1000),
            )

        # 构建兴趣标签
        interests = ""
        if input.interests:
            interests = " ".join(input.interests)
        elif input.user_preferences and isinstance(input.user_preferences.get("interests"), list):
            interests = "".join(input.user_preferences["interests"])

        # LLM 动态 query 生成（当有约束时）
        attraction_query = f"{input.city} 必去 景点 {interests}".strip()
        food_query = f"{input.city} 美食 推荐 {interests}".strip()
        if input.constraints:
            # 用 LLM 根据约束改写 query
            attraction_query, food_query = await self._rewrite_queries(
                input.city, interests, input.constraints
            )
        # 酒店预算估算
        hotel_budget = None
        if input.budget and input.days and input.days > 0:
            hotel_budget = round(input.budget / input.days / 1.5)

        # 构建并行任务
        bundle = await self._parallel_search(
            city=input.city,
            interests=interests,
            hotel_budget=hotel_budget,
            departure_city=input.departure_city,
            attraction_query=attraction_query,
            food_query=food_query,
        )

        # 缓存写入
        await bundle_cache.set(
            input.city, input.budget, input.days,
            input.departure_city, input.user_preferences,
            bundle.to_dict(),
        )

        duration_ms = int((time.time() - _t0) * 1000)
        logger.info("research_agent|done city=%s duration=%dms", input.city, duration_ms)

        return AgentOutput(
            agent_name=self.name,
            result=bundle,
            duration_ms=duration_ms,
        )

    async def _rewrite_queries(
        self, city: str, interests: str, constraints: str
    ) -> tuple[str, str]:
        """用 LLM 根据用户约束改写搜索 query。

        例如："不要爬山" → query 中排除山景类，加入"平地/公园/博物馆"
        """
        try:
            prompt = (
                f"用户想去{city}旅游，约束：{constraints}。\n"
                f"请生成两个搜索 query（景点和美食），每个不超过 15 字。\n"
                f"输出 JSON: {{\"attraction_query\": \"...\", \"food_query\": \"...\"}}\n"
                f"只输出 JSON。"
            )
            from langchain_core.messages import HumanMessage
            resp = await self.llm.ainvoke([HumanMessage(content=prompt)])
            content = resp.content if isinstance(resp.content, str) else ""
            import json
            result = json.loads(content.strip())
            return (
                result.get("attraction_query", f"{city} 景点 {interests}"),
                result.get("food_query", f"{city} 美食 {interests}"),
            )
        except Exception as e:
            logger.warning("research_agent|query_rewrite_failed: %s", e)
            return (f"{city} 必去 景点 {interests}", f"{city} 美食 推荐 {interests}")

    async def _parallel_search(
        self,
        city: str,
        interests: str,
        hotel_budget: Optional[int],
        departure_city: Optional[str],
        attraction_query: Optional[str] = None,
        food_query: Optional[str] = None,
    ) -> ResearchBundle:
        """并行执行所有搜索任务。

        Args:
            city: 目标城市
            interests: 兴趣标签字符串
            hotel_budget: 酒店预算
            departure_city: 出发城市

        Returns:
            ResearchBundle 候选池
        """
        from src.services.agent.tools import (
            retrieve_knowledge_tool,
            search_hotels_tool,
            calculate_distance_tool,
        )
        from src.services.mcp.amap_client import call_tool as amap_call_tool

        # 定义并行任务
        tasks = []
        task_keys = []
        task_names = []

        # 任务1：景点
        _attr_query = attraction_query or f"{city} 必去 景点 {interests}".strip()

        async def task_attractions():
            return await retrieve_knowledge_tool.ainvoke({
                "query": _attr_query,
                "city": city,
                "category": "attraction",
            })
        tasks.append(task_attractions())
        task_keys.append("attractions")
        task_names.append("retrieve_knowledge")

        # 任务2：美食
        _food_query = food_query or f"{city} 美食 推荐 {interests}".strip()

        async def task_food():
            return await retrieve_knowledge_tool.ainvoke({
                "query": _food_query,
                "city": city,
                "category": "food",
            })
        tasks.append(task_food())
        task_keys.append("food")
        task_names.append("retrieve_knowledge")

        # 任务3：酒店
        async def task_hotels():
            return await search_hotels_tool.ainvoke({
                "city": city,
                "budget": hotel_budget,
            })
        tasks.append(task_hotels())
        task_keys.append("hotels")
        task_names.append("search_hotels")

        # 任务4：天气
        async def task_weather():
            try:
                return await amap_call_tool("maps_weather", {"city": city})
            except Exception:
                return WEATHER_FALLBACK
        tasks.append(task_weather())
        task_keys.append("weather")
        task_names.append("maps_weather")

        # 任务5：距离（有出发城市时）
        if departure_city:
            async def task_distance():
                try:
                    return await calculate_distance_tool.ainvoke({
                        "from": departure_city,
                        "to": city,
                    })
                except Exception:
                    return DISTANCE_FALLBACK
            tasks.append(task_distance())
            task_keys.append("distance")
            task_names.append("calculate_distance")

        # 发送 tool_start 事件（带 key 区分同名工具，如两次 retrieve_knowledge）
        if self.on_event:
            for name, key in zip(task_names, task_keys):
                await self.on_event({"type": "tool_start", "name": name, "key": key})

        # 并行执行（包装为完成即发 tool_end，前端可逐个点亮）
        async def _with_end_event(coro, name: str, key: str):
            try:
                return await coro
            finally:
                if self.on_event:
                    try:
                        await self.on_event({"type": "tool_end", "name": name, "key": key})
                    except Exception:
                        pass

        wrapped = [
            _with_end_event(t, task_names[i], task_keys[i])
            for i, t in enumerate(tasks)
        ]

        _t0 = time.time()
        results = await asyncio.gather(*wrapped, return_exceptions=True)
        _t_total = int((time.time() - _t0) * 1000)
        logger.info("research_agent|parallel tools=%d duration=%dms city=%s",
                    len(tasks), _t_total, city)

        # 组装 bundle
        fallbacks = {
            "attractions": ATTRACTION_FALLBACK,
            "food": FOOD_FALLBACK,
            "hotels": HOTEL_FALLBACK,
            "weather": WEATHER_FALLBACK,
            "distance": DISTANCE_FALLBACK,
        }

        bundle_data = {}
        for i, key in enumerate(task_keys):
            result = results[i]
            if isinstance(result, Exception):
                logger.warning("research_agent|tool_failed key=%s error=%s", key, result)
                bundle_data[key] = fallbacks.get(key, "信息暂时不可用。")
            else:
                bundle_data[key] = result

        # 从格式化文本中提取结构化 POI 数据（用于封闭世界约束）
        attraction_text = bundle_data.get("attractions", "")
        food_text = bundle_data.get("food", "")
        attraction_items = self._extract_spot_items(attraction_text, "attraction")
        food_items = self._extract_spot_items(food_text, "food")
        logger.info(
            "research_agent|extracted_items attractions=%d food=%d",
            len(attraction_items), len(food_items),
        )

        return ResearchBundle(
            attractions=bundle_data.get("attractions"),
            food=bundle_data.get("food"),
            hotels=bundle_data.get("hotels"),
            weather=bundle_data.get("weather"),
            distance=bundle_data.get("distance"),
            attraction_items=attraction_items,  # 新增结构化字段
            food_items=food_items,              # 新增结构化字段
        )
