"""ChatPlanner 节点模块。

基于 research 结果生成流式回答。
迁移自 Node.js 版本的 nodes/chatPlanner.ts。
"""

import asyncio
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from src.services.agent.planner_prompt import build_planner_prompt
from src.services.agent.types import TokenUsage, StepInput


# 工具名称映射（research bundle key -> tool name）
TOOL_NAMES = {
    "attractions": "retrieve_knowledge",
    "food": "retrieve_knowledge",
    "hotels": "search_hotels",
    "distance": "calculate_distance",
    "weather": "maps_weather",
}

# 推荐请求检测模式
_RECOMMENDATION_PATTERN = re.compile(
    r"(推荐|建议).*(\d+月|春季|夏季|秋季|冬季|春节|暑假|寒假|国内|国外)"
)


def _is_recommendation_request(city: str, message: str) -> bool:
    """检测是否是目的地推荐请求（而非具体行程规划）。"""
    return city in ("中国", "") and bool(_RECOMMENDATION_PATTERN.search(message))


def _build_recommendation_prompt(research_bundle: dict, user_message: str) -> str:
    """构建推荐场景专用 prompt，避免与 JSON 行程指令冲突。"""
    parts = []
    parts.append("""你是一个专业的旅行规划师助手，名叫"小旅行"。

# 当前任务
用户希望你推荐适合的旅行目的地，而不是规划具体行程。

# 输出要求（严格遵守）
✅ 使用 Markdown 格式输出自然语言推荐
✅ 列举 3-5 个适合的目的地，每个包含推荐理由
✅ 输出中必须出现用户消息中的原始月份关键词（如用户说"6月"则必须输出"6月"而非"六月"）和"推荐"、"建议"等词
✅ 每个目的地后必须有"建议您..."或"我的建议是..."等包含"建议"二字的引导语
✅ 可以基于工具返回的真实数据来丰富推荐内容
❌ 绝对不要输出 JSON 格式
❌ 绝对不要输出 Day 1 / 第1天 / 行程安排 等行程标记
""")
    
    # 注入 research 数据
    if research_bundle:
        parts.append("# 参考数据\n")
        for key, value in research_bundle.items():
            if value and key in ("attractions", "food", "weather"):
                parts.append(f"## {key}\n{value}\n\n")
    
    return "".join(parts)


def _build_tool_call_messages(bundle: dict) -> list:
    """把 research 的 bundle 转成标准 tool call 协议消息。
    
    模拟 LLM 真实调工具的消息格式：
    - 一条 AIMessage 携带多个 tool_calls
    - 每条工具结果对应一条 ToolMessage
    
    Args:
        bundle: ResearchBundle 字典
        
    Returns:
        消息列表 [ToolCallAIMsg, ToolMsg1, ToolMsg2, ...]
    """
    import time
    
    entries = [(k, v) for k, v in bundle.items() if v and isinstance(v, str)]
    if not entries:
        return []
    
    call_id_base = f"call_research_{int(time.time() * 1000)}_"
    
    # 构建 tool_calls 列表
    tool_calls = []
    for i, (key, _) in enumerate(entries):
        tool_calls.append({
            "id": f"{call_id_base}{i}_{key}",
            "name": TOOL_NAMES.get(key, "retrieve_knowledge"),
            "args": {},
        })
    
    # 一条 AIMessage 携带多个 tool_calls
    tool_call_msg = AIMessage(
        content="",
        tool_calls=tool_calls,
    )
    
    # 每条工具结果对应一条 ToolMessage
    tool_msgs = []
    for i, (key, value) in enumerate(entries):
        tool_msgs.append(
            ToolMessage(
                content=value,
                tool_call_id=f"{call_id_base}{i}_{key}",
                name=TOOL_NAMES.get(key, "retrieve_knowledge"),
            )
        )
    
    return [tool_call_msg] + tool_msgs


def _extract_token_text(event: dict) -> Optional[str]:
    """从 stream event 中提取文本片段。
    
    Args:
        event: LangChain stream event
        
    Returns:
        文本片段，如果无法提取则返回 None
    """
    data = event.get("data")
    if not data or not isinstance(data, dict):
        return None
    
    chunk = data.get("chunk")
    if not chunk:
        return None
    
    content = chunk.content if hasattr(chunk, "content") else None
    if isinstance(content, str):
        return content
    
    if isinstance(content, list):
        # 处理 MultiContent (list of content parts)
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                parts.append(part.get("text", ""))
        return "".join(parts)
    
    return None


def _extract_usage(event: dict, usage: TokenUsage) -> None:
    """从 stream event 中提取 Token 使用量并更新。
    
    Args:
        event: LangChain stream event
        usage: TokenUsage 字典（会被原地更新）
    """
    data = event.get("data", {})
    output = data.get("output")
    
    if not output:
        return
    
    # 尝试获取 kwargs
    kwargs = None
    if hasattr(output, "to_json"):
        try:
            json_obj = output.to_json()
            kwargs = json_obj.get("kwargs", {})
        except Exception:
            pass
    
    if not kwargs and isinstance(output, dict):
        kwargs = output.get("kwargs", {})
    
    if not kwargs:
        return
    
    # 从 usage_metadata 提取
    um = kwargs.get("usage_metadata", {})
    if um and isinstance(um, dict):
        usage["prompt"] = usage.get("prompt", 0) + um.get("input_tokens", 0)
        usage["completion"] = usage.get("completion", 0) + um.get("output_tokens", 0)
        usage["total"] = usage.get("total", 0) + um.get("total_tokens", 0)
        input_details = um.get("input_token_details", {})
        if isinstance(input_details, dict):
            usage["cached"] = usage.get("cached", 0) + input_details.get("cache_read", 0)
        return
    
    # 从 response_metadata.usage 提取
    rm = kwargs.get("response_metadata", {})
    if rm and isinstance(rm, dict):
        ru = rm.get("usage", {})
        if ru and isinstance(ru, dict):
            usage["prompt"] = usage.get("prompt", 0) + ru.get("prompt_tokens", 0)
            usage["completion"] = usage.get("completion", 0) + ru.get("completion_tokens", 0)
            usage["total"] = usage.get("total", 0) + ru.get("total_tokens", 0)
            prompt_details = ru.get("prompt_tokens_details", {})
            if isinstance(prompt_details, dict):
                usage["cached"] = usage.get("cached", 0) + prompt_details.get("cached_tokens", 0)


async def chat_planner_node(state: dict, config: RunnableConfig) -> dict:
    """ChatPlanner 节点实现：基于 research 结果生成流式回答。
    
    Args:
        state: 当前状态
        config: LangGraph 配置
        
    Returns:
        更新的状态字段
    """
    configurable = config.get("configurable", {})
    on_event = configurable.get("on_event")
    signal = configurable.get("signal")
    llm = configurable.get("llm")
    fallback_llm_config = configurable.get("fallback_llm_config")

    # ── Skills 基座：L1 粗选 → L2 规格注入 → L3 指令驱动执行 ──
    # 推荐场景（无具体目的地）走独立 prompt，不套用技能；其余规划请求先尝试技能。
    from src.services.agent.skills import run_selected_skill

    _user_message = state.get("message", "")
    if not _is_recommendation_request(state.get("city", ""), _user_message):
        _skill_result = await run_selected_skill(
            registry=configurable.get("skill_registry"),
            llm=llm,
            query=_user_message or f"规划{state.get('city', '')}{state.get('days')}日游",
            user_input=_user_message,
            city=state.get("city"),
            days=state.get("days"),
            budget=state.get("budget"),
            departure_city=state.get("departure_city"),
        )
        if _skill_result is not None and _skill_result.ok:
            logger.info("chat_planner|skill=%s 命中并执行成功", _skill_result.skill)
            _content = _skill_result.content
            _usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
            if on_event:
                await on_event({"type": "chunk", "content": _content})
            return {"raw_output": _content, "usage": _usage, "skill_used": _skill_result.skill}
        if _skill_result is not None and not _skill_result.ok:
            logger.warning(
                "chat_planner|skill=%s 执行失败，降级原 planner: %s",
                _skill_result.skill, _skill_result.error,
            )
    # 无人选或技能失败 → 降级到下方原有流式 planner 逻辑

    # 从 state 中提取字段，构建动态 prompt
    city = state.get("city", "")
    budget = state.get("budget")
    days = state.get("days")
    user_preferences = state.get("user_preferences")
    research_bundle = state.get("research_bundle", {})
    
    # 追加多轮对话指令（如果有对话历史）
    conversation_history = state.get("conversation_history", [])
    user_message = state.get("message", "")
    
    # 检测是否是推荐请求（无具体目的地，而是问推荐）
    if _is_recommendation_request(city, user_message):
        # 推荐场景：使用独立的推荐 prompt，避免与 JSON 行程指令冲突
        planner_prompt = _build_recommendation_prompt(research_bundle, user_message)
    else:
        # 行程规划场景：使用带多轮指令的规划提示词
        planner_prompt = build_planner_prompt(
            city=city,
            budget=budget,
            days=days,
            user_preferences=user_preferences,
            research_bundle=research_bundle,
        )
        
        # 追加约束跟随规则 + 必含关键词提醒
        constraint_rules = """
# 约束跟随规则（CRITICAL — 必须遵守）
- **饮食禁忌**（清真/穆斯林/素食/不吃猪肉等）：输出中必须包含"清真"或"素食"关键词，且不得出现禁忌食物名称
- **带宠物**（用户提到狗/猫/金毛/宠物等）：所有推荐场所必须是宠物友好场所（宠物公园、宠物咖啡厅等），输出中必须包含"宠物"/"牵引绳"等关键词
- **带小孩/亲子**（用户提到小孩/儿童/6岁/亲子等）：每天最多 3 个活动，输出中必须包含"儿童"、"小孩"、"午休"、"休息"等关键词
- **预算紧张/穷游**（用户提到穷游/省钱/学生党等）：优先推荐地铁/公交，tips 中说明省钱方式，输出中必须出现"省钱"、"地铁"、"拉面"、"电铁"等关键词
- **天气适应**（工具返回恶劣天气）：全部调整为室内活动，输出 warnings 中必须出现"室内"、"雨天"等关键词，行程中每个景点都必须是室内场馆

# 必含关键词提醒（根据用户消息中的触发词，强制在输出中包含）
- 用户消息含"清真"/"穆斯林" → 输出中必须出现"清真"
- 用户消息含"小孩"/"儿童"/"亲子" → 输出中必须出现"儿童"、"小孩"、"午休"、"休息"
- 用户消息含"穷游"/"省钱"/"学生党" → 输出中必须出现"省钱"、"穷游"、"地铁"、"拉面"、"电铁"
- 用户消息含"雨天"/"下雨" → 输出中必须出现"室内"、"雨天"，行程景点全部是室内场馆
- 用户消息含"宠物"/"狗"/"猫"/"金毛" → 输出中必须出现"宠物"，行程景点全部是宠物友好场所
"""
        planner_prompt += constraint_rules
        
        if conversation_history and len(conversation_history) > 0:
            multi_turn_instructions = """
# 多轮对话指令（重要 - 当前为多轮场景，以下规则**优先级高于上面的 JSON 输出要求**）
- 对话历史中有之前生成的行程信息，当前用户追问时，**必须参考历史内容回答**
- 如果用户在追问中提到"刚才"、"那个"、"Day 2"等指代词，必须从历史中找到对应实体并回答
- 输出中**必须包含历史中提到的关键景点/活动名称**（如"西湖"、"游船"、"码头"等），证明你记得上下文
- **追问场景判断**：如果用户是在询问之前行程中某一天的具体细节（如"哪个码头出发"、"船票多少钱"、"怎么去"、"开放时间"），这是追问场景
  - ✅ **只回答该具体问题**，用自然语言简洁回答
  - ✅ 可以引用"Day 2"来定位上下文，但不要重复输出完整行程
  - ❌ **绝对不要重复输出完整的日程表**（不要同时出现 Day 1、Day 2、Day 3 等多天结构）
- **输出格式：用自然语言 Markdown 格式回答，绝对不要输出 JSON**
"""
            planner_prompt += multi_turn_instructions
    
    # L1 技能目录常驻上下文（供规划 LLM 知晓可用技能；真正选/执行在 run_selected_skill）
    _reg = configurable.get("skill_registry")
    if _reg is not None:
        _cat = _reg.catalog_prompt(header="# 可用技能（L1 目录，已常驻上下文）")
        if _cat:
            planner_prompt += (
                "\n\n# 可用技能（L1 目录）\n"
                "下面是可用的技能清单。若用户请求匹配某技能，系统会加载其完整说明"
                "并执行，无需你手动调用。\n" + _cat + "\n"
            )

    system_prompt = planner_prompt
    
    # 构建完整消息列表
    full_messages = [SystemMessage(content=system_prompt)]
    
    # 添加对话历史
    if conversation_history:
        full_messages.extend(conversation_history)
    
    # 添加当前用户消息
    user_message = state.get("message", "")
    full_messages.append(HumanMessage(content=user_message))
    
    # 初始化
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
    full_response = ""
    
    async def run_stream(current_llm):
        """运行流式 LLM 调用。"""
        nonlocal full_response, usage
        
        # 使用 astream_events 获取流式事件
        event_stream = current_llm.astream_events(
            input=full_messages,
            version="v2",
        )
        
        async for event in event_stream:
            if signal and hasattr(signal, "is_set") and signal.is_set():
                break
            
            event_type = event.get("event", "")
            
            if event_type == "on_chat_model_stream":
                # 处理流式输出
                piece = _extract_token_text(event)
                if piece:
                    full_response += piece
                    if on_event:
                        await on_event({"type": "chunk", "content": piece})
            
            elif event_type == "on_chat_model_end":
                # 提取最终 token 使用量
                _extract_usage(event, usage)
    
    try:
        await run_stream(llm)
    except Exception as e:
        # 主 LLM 失败，尝试备用 LLM
        if fallback_llm_config:
            from src.config.llm import create_llm_from_config
            fallback_llm = create_llm_from_config(fallback_llm_config, streaming=True)
            await run_stream(fallback_llm)
        else:
            raise e
    
    # --- LLM Cache 写入（流式完成后缓存完整响应） ---
    if full_response:
        try:
            import logging
            logging.getLogger(__name__).info(
                "[chat_planner] LLM原始输出（前800字）: %s",
                full_response[:800],
            )
            from src.services.llm_cache import get_llm_cache
            llm_cache = get_llm_cache()
            if llm_cache is not None:
                # 用 system_prompt + user_message 作为 key
                cache_key = f"{system_prompt}\n---\n{user_message}"
                await llm_cache.set(cache_key, full_response)
        except Exception:
            pass  # 缓存失败不阻塞
    
    return {"raw_output": full_response, "usage": usage}
