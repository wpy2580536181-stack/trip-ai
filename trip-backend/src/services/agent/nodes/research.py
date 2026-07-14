"""Research 节点模块。

并行调用工具获取情报（景点、美食、酒店、天气、距离）。
迁移自 Node.js 版本的 nodes/research.ts。
"""

import asyncio
import logging
import time
from typing import Any, Callable, Awaitable

from langchain_core.runnables import RunnableConfig

from src.services.agent.types import ResearchBundle, StepInput

logger = logging.getLogger(__name__)


# 工具调用失败时的降级消息
HOTEL_FALLBACK = "住宿信息暂时不可用，请基于通用旅行知识回答。"
DISTANCE_FALLBACK = "距离计算暂时不可用。"
WEATHER_FALLBACK = "天气服务暂时不可用，请根据季节常识判断。"


async def research_node(state: dict, config: RunnableConfig) -> dict:
    """Research 节点实现：并行调用工具获取情报。
    
    Args:
        state: 当前状态
        config: LangGraph 配置（包含 trace_recorder, on_event, signal 等）
        
    Returns:
        更新的状态字段（research_bundle）
    """
    from ..tools import retrieve_knowledge_tool, search_hotels_tool, calculate_distance_tool
    from ...mcp.amap_client import call_tool as amap_call_tool
    from ..types import PlannerConfig
    from ..research_bundle_cache import get_bundle_cache
    
    city = state.get("city", "")
    budget = state.get("budget")
    days = state.get("days")
    departure_city = state.get("departure_city")
    user_preferences = state.get("user_preferences")
    
    # ---- ResearchBundle 全量缓存检查 ----
    bundle_cache = get_bundle_cache()
    cached_bundle = await bundle_cache.get(city, budget, days, departure_city, user_preferences)
    if cached_bundle is not None:
        logger.info("bundle_cache|returning_cached city=%s days=%d", city, days)
        return {"research_bundle": cached_bundle}
    
    # 从 config 中获取依赖
    configurable = config.get("configurable", {})
    trace_recorder = configurable.get("trace_recorder")
    on_event = configurable.get("on_event")
    step_counter = configurable.get("step_counter")
    
    # 构建兴趣标签字符串
    interests = ""
    if isinstance(user_preferences, dict) and "interests" in user_preferences:
        prefs_interests = user_preferences["interests"]
        if isinstance(prefs_interests, list):
            interests = "".join(prefs_interests)
    
    # 酒店预算估算
    hotel_budget = None
    if budget is not None and days is not None and days > 0:
        hotel_budget = round(budget / days / 1.5)
    
    # 定义并行任务
    # 每个任务是一个协程函数
    tasks = []
    task_names = []
    task_keys = []
    
    # 任务1：检索景点
    async def task_attractions():
        return await retrieve_knowledge_tool.ainvoke({
            "query": f"{city} 必去 景点 {interests}".strip(),
            "city": city,
            "category": "attraction",
        })
    tasks.append(task_attractions())
    task_names.append("retrieve_knowledge")
    task_keys.append("attractions")
    
    # 任务2：检索美食
    async def task_food():
        return await retrieve_knowledge_tool.ainvoke({
            "query": f"{city} 美食 推荐 {interests}".strip(),
            "city": city,
            "category": "food",
        })
    tasks.append(task_food())
    task_names.append("retrieve_knowledge")
    task_keys.append("food")
    
    # 任务3：搜索酒店
    async def task_hotels():
        return await search_hotels_tool.ainvoke({
            "city": city,
            "budget": hotel_budget,
        })
    tasks.append(task_hotels())
    task_names.append("search_hotels")
    task_keys.append("hotels")
    
    # 任务4：查询天气（通过高德 MCP）
    async def task_weather():
        try:
            return await amap_call_tool("maps_weather", {"city": city})
        except Exception:
            return WEATHER_FALLBACK
    tasks.append(task_weather())
    task_names.append("maps_weather")
    task_keys.append("weather")
    
    # 任务5：计算距离（如果有出发城市）
    if departure_city:
        async def task_distance():
            return await calculate_distance_tool.ainvoke({
                "from": departure_city,
                "to": city,
            })
        tasks.append(task_distance())
        task_names.append("calculate_distance")
        task_keys.append("distance")
    
    # 记录每个任务的起始时间
    start_times = [asyncio.get_event_loop().time() for _ in tasks]
    
    # 发送 tool_start 事件
    for i, name in enumerate(task_names):
        if trace_recorder and step_counter:
            trace_recorder.add({
                "step": step_counter["value"],
                "type": "tool_start",
                "name": name,
            })
            step_counter["value"] += 1
        
        if on_event:
            await on_event({
                "type": "tool_start",
                "name": name,
            })
    
    # 并行执行所有任务
    _t0 = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    _t_total = time.time()
    
    # 记录 per-tool 耗时
    for i, key in enumerate(task_keys):
        tool_name = task_names[i]
        duration_ms = int((_t_total - start_times[i]) * 1000)
        is_error = isinstance(results[i], Exception)
        logger.info(
            "research|tool=%s key=%s duration=%dms error=%s city=%s",
            tool_name, key, duration_ms, is_error, city,
        )
    logger.info("research|total=%dms tools=%d city=%s",
                int((_t_total - _t0) * 1000), len(tasks), city)
    
    # 构建 ResearchBundle
    bundle: ResearchBundle = {}
    fallbacks = {
        "attractions": "景点信息暂时不可用，请基于通用旅行知识回答。",
        "food": "美食信息暂时不可用，请基于通用旅行知识回答。",
        "hotels": HOTEL_FALLBACK,
        "weather": WEATHER_FALLBACK,
        "distance": DISTANCE_FALLBACK,
    }
    
    for i, key in enumerate(task_keys):
        result = results[i]
        if isinstance(result, Exception):
            bundle[key] = fallbacks.get(key, "信息暂时不可用。")
        else:
            bundle[key] = result
        
        # 记录 tool_end
        if trace_recorder and step_counter:
            duration_ms = int((asyncio.get_event_loop().time() - start_times[i]) * 1000)
            trace_recorder.add({
                "step": step_counter["value"],
                "type": "tool_end",
                "name": task_names[i],
                "duration_ms": duration_ms,
            })
            step_counter["value"] += 1
    
    # 发送 tool_end 事件
    for name in task_names:
        if on_event:
            await on_event({
                "type": "tool_end",
                "name": name,
                "output": bundle.get(key, ""),
            })
    
    # ---- ResearchBundle 全量缓存写入 ----
    await bundle_cache.set(city, budget, days, departure_city, user_preferences, bundle)
    
    return {"research_bundle": bundle}
