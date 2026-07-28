"""Agent Engine 模块。

LangGraph 多智能体编排引擎。
迁移自 Node.js 版本的 agentEngine.ts。
"""

import asyncio
import logging
import time
import uuid
from typing import Any, Callable, Awaitable, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from src.config.settings import settings
from src.config.llm import create_llm, load_fallback_llm_config
from src.services.conversation_service import load_context
from src.config.database import async_session
from src.services.agent.state import PlannerState
from src.services.agent.types import TokenUsage, StepInput
from src.services.agent.chat_graph import build_chat_graph
from src.services.agent.planner_graph import build_planner_graph
from src.services.agent.orchestrator import Orchestrator
from src.services.agent.schemas import PlanRequest
from src.services.agent.trace_recorder import TraceRecorder
from src.services.agent.token_monitor import token_monitor
from src.services.agent.token_tracker import LLMContext
from src.services.agent.skills import get_skill_registry, load_builtin_skills, SkillContext, SkillResult


# AgentEngine 单例
_agent_engine: Optional["AgentEngine"] = None


def get_agent_engine() -> "AgentEngine":
    """获取 AgentEngine 单例。
    
    Returns:
        AgentEngine 实例
    """
    global _agent_engine
    if _agent_engine is None:
        _agent_engine = AgentEngine()
    return _agent_engine


class AgentEngine:
    """LangGraph 多智能体编排引擎。
    
    功能：
    - chat(): 多轮对话（使用 ChatGraph）
    - recommend(): 行程推荐（使用 PlannerGraph）
    """
    
    def __init__(self):
        """初始化 AgentEngine。"""
        # 创建主 LLM 实例
        self.llm = create_llm(streaming=True)
        
        # 加载备用 LLM 配置
        self.fallback_llm_config = load_fallback_llm_config()
        
        # 工具缓存（per-tool 独立 TTL + size）
        from src.services.agent.tool_cache import get_tool_cache
        self.tool_cache = get_tool_cache()
        
        # 高德 MCP 工具（延迟初始化）
        self.amap_tools: list = []
        self.amap_tools_init_promise: Optional[asyncio.Task] = None

        # 技能注册表（三层渐进式披露；从 skills/skills/<name>/SKILL.md 加载内置技能）
        self.skill_registry = get_skill_registry()
        load_builtin_skills(self.skill_registry)
    
    async def ensure_amap_tools(self) -> None:
        """确保高德 MCP 工具已加载。"""
        if self.amap_tools_init_promise is None:
            self.amap_tools_init_promise = asyncio.create_task(
                self._load_amap_tools()
            )
        await self.amap_tools_init_promise
    
    async def _load_amap_tools(self) -> None:
        """加载高德 MCP 工具。"""
        try:
            from src.services.mcp.tool_loader import load_amap_tools
            self.amap_tools = await load_amap_tools()
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"高德 MCP 工具加载失败: {e}")
            self.amap_tools = []
    
    # ------------------------------------------------------------------
    # Skills 基座能力（三层渐进式披露）
    # ------------------------------------------------------------------
    async def invoke_skill(
        self,
        name: str,
        user_input: str = "",
        ctx: Optional[SkillContext] = None,
        **kwargs: Any,
    ) -> SkillResult:
        """调用已注册技能（三层渐进式披露：L1 目录 → L2 规格 → L3 执行）。

        这是 agent 调用 skills 的统一入口。技能执行是「指令驱动」的：把
        SKILL.md 的 instructions 交给 LLM，由 LLM 借助底层工具（tool calling）
        自行编排，而非写死的代码流程。具体由哪个节点选择技能在后续步骤完成。

        Args:
            name: 技能名称
            user_input: 用户原始输入（用于拼装执行提示词）
            ctx: 执行上下文（缺省时自动装配 llm + 底层工具）
            **kwargs: 技能入参

        Returns:
            SkillResult
        """
        if ctx is None:
            from src.services.agent.tools import (
                retrieve_knowledge,
                search_hotels,
                calculate_distance,
            )

            ctx = SkillContext(
                llm=self.llm,
                tools=[retrieve_knowledge, search_hotels, calculate_distance],
                registry=self.skill_registry,
                user_input=user_input,
            )
        return await self.skill_registry.execute(name, ctx, **kwargs)

    def skill_catalog_prompt(self, header: str = "# 可用技能") -> str:
        """获取 L1 技能目录的提示词片段（供注入 planner/系统提示词）。

        Args:
            header: 段标题

        Returns:
            渲染后的提示词片段；无技能时返回空串
        """
        return self.skill_registry.catalog_prompt(header=header)

    async def _load_user_preferences(self, user_id: int) -> Optional[dict]:
        """加载用户偏好设置。
        
        Args:
            user_id: 用户 ID
            
        Returns:
            用户偏好字典，如果加载失败则返回 None
        """
        try:
            from src.models.user import User
            from src.config.database import async_session
            
            import asyncio
            loop = asyncio.get_event_loop()
            # 在线程池中执行同步数据库查询
            result = await loop.run_in_executor(
                None,
                self._sync_load_preferences,
                user_id,
            )
            return result
        except Exception:
            return None
    
    def _sync_load_preferences(self, user_id: int) -> Optional[dict]:
        """同步加载用户偏好（用于线程池执行）。"""
        try:
            from sqlalchemy import select
            from src.config.database import sync_session
            
            with sync_session() as session:
                stmt = select(User).where(User.id == user_id)
                user = session.execute(stmt).scalar_one_or_none()
                if user and user.preferences:
                    return user.preferences
            return None
        except Exception:
            return None
    
    def _db_messages_to_langchain(self, messages: list[dict]) -> list:
        """将数据库消息转换为 LangChain 消息格式。
        
        Args:
            messages: 数据库消息列表 [{"role": "user", "content": "..."}, ...]
            
        Returns:
            LangChain 消息对象列表
        """
        langchain_msgs = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role == "user":
                langchain_msgs.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_msgs.append(AIMessage(content=content))
            elif role == "system":
                langchain_msgs.append(SystemMessage(content=content))
        
        return langchain_msgs
    
    async def chat(
        self,
        user_id: int,
        message: str,
        conversation_id: Optional[int] = None,
        on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
        signal: Optional[asyncio.Event] = None,
        message_id: int = 0,
        trip_context: Optional[str] = None,
    ) -> dict:
        """多轮对话（使用 ChatAgent）。
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            conversation_id: 对话 ID（可选）
            on_event: 事件回调函数
            signal: 中止信号
            message_id: 消息 ID（用于 Trace 落表）
            trip_context: 行程摘要上下文（可选，由 trip_service 构建）
            
        Returns:
            包含 reply 和 conversation_id 的字典
        """
        await self.ensure_amap_tools()
        
        start_time = time.time()
        
        # 加载用户偏好
        preferences = await self._load_user_preferences(user_id)
        
        # 加载对话上下文
        system_summary = None
        conversation_recap = None
        conversation_history: list = []
        
        if conversation_id:
            try:
                async with async_session() as session:
                    ctx = await load_context(session, conversation_id)
                    system_summary = ctx.get("system_summary")
                    conversation_recap = ctx.get("conversation_recap")
                    recent_messages = ctx.get("recent_messages", [])
                    conversation_history = self._db_messages_to_langchain(recent_messages)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("load_context failed: %s", e)
        
        # 构建系统提示词（注入 L1 技能目录，常驻上下文）
        from .system_prompt import build_system_prompt
        system_prompt = build_system_prompt(
            user_preferences=preferences,
            conversation_summary=system_summary,
            conversation_recap=conversation_recap,
            skill_catalog=self.skill_catalog_prompt(),
        )
        
        # 创建 TraceRecorder
        trace_recorder = TraceRecorder(message_id)
        
        # 构建 ChatAgent（多 Agent 架构）
        from src.services.agent.agents.chat_agent import ChatAgent
        chat_agent = ChatAgent(
            llm=self.llm,
            on_event=on_event,
            system_prompt=system_prompt,
        )
        
        try:
            # 执行 ChatAgent（设置 LLM 上下文，供 token_tracker callback 使用）
            with LLMContext(user_id=user_id, endpoint="chat"):
                result = await chat_agent.run(
                    message=message,
                    conversation_history=conversation_history,
                    system_prompt=system_prompt,
                    trip_context=trip_context,
                )
            
            if result.error:
                raise ValueError(result.error)
            
            # 记录完成事件
            trace_recorder.add({
                "step": 1,
                "type": "complete",
                "duration_ms": result.duration_ms,
            })
            await trace_recorder.flush()
            
            # 记录 Token 使用量（后台任务，不阻塞）
            asyncio.create_task(token_monitor.record({
                "request_type": "chat",
                "route": "chat_agent",
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "total_usage": result.usage,
                "latency_ms": result.duration_ms,
                "timestamp": int(time.time() * 1000),
            }))
            
            # 发送完成事件
            if on_event:
                await on_event({
                    "type": "complete",
                    "content": result.result or "",
                    "usage": result.usage,
                })
            
            return {
                "reply": result.result or "",
                "conversation_id": conversation_id,
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # 记录错误
            trace_recorder.add({
                "step": 1,
                "type": "error",
                "error": error_msg,
            })
            await trace_recorder.flush()
            
            # 发送错误事件
            if on_event:
                await on_event({
                    "type": "error",
                    "error": error_msg,
                })
            
            raise
    
    async def recommend(
        self,
        user_id: int,
        city: str,
        budget: int,
        days: int,
        departure_city: Optional[str] = None,
        conversation_id: Optional[int] = None,
        on_event: Optional[Callable[[dict], Awaitable[None]]] = None,
        message_id: int = 0,
    ) -> dict:
        """行程推荐（使用多 Agent Orchestrator）。
        
        Args:
            user_id: 用户 ID
            city: 目标城市
            budget: 预算（元）
            days: 天数
            departure_city: 出发城市（可选）
            conversation_id: 对话 ID（可选）
            on_event: 事件回调函数
            message_id: 消息 ID（用于 Trace 落表）
            
        Returns:
            包含 reply 和 parsed 的字典
        """
        # 并行加载 Amap 工具和用户偏好（两者互不依赖）
        _, preferences = await asyncio.gather(
            self.ensure_amap_tools(),
            self._load_user_preferences(user_id),
        )
        
        start_time = time.time()
        
        # 创建 TraceRecorder
        trace_recorder = TraceRecorder(message_id)
        
        # 构建输入消息
        input_message = (
            f"请为我规划{departure_city + '出发到' if departure_city else ''}"
            f"{city}{days}日游行程，预算{budget}元。"
        )
        
        # 构建 fallback LLM
        fallback_llm = None
        if self.fallback_llm_config:
            from src.config.llm import create_llm_from_config
            fallback_llm = create_llm_from_config(self.fallback_llm_config, streaming=False)
        
        # 构建 Orchestrator（多 Agent 编排）
        orchestrator = Orchestrator(
            llm=self.llm,
            fallback_llm=fallback_llm,
            on_event=on_event,
        )
        
        # 构建规划请求
        request = PlanRequest(
            user_id=user_id,
            city=city,
            days=days,
            budget=budget,
            departure_city=departure_city,
            preferences=preferences,
            message=input_message,
        )
        
        try:
            # 执行多 Agent 编排（设置 LLM 上下文，供 token_tracker callback 使用）
            with LLMContext(user_id=user_id, endpoint="recommend"):
                result = await orchestrator.plan(request)
            
            logger = logging.getLogger(__name__)
            logger.info(
                "agent|orchestrator=%dms city=%s days=%d budget=%d passed=%s",
                result.duration_ms, city, days, budget,
                result.review.passed if result.review else False,
            )
            
            if result.error:
                raise ValueError(result.error)
            
            # 记录完成事件
            trace_recorder.add({
                "step": 1,
                "type": "complete",
                "duration_ms": result.duration_ms,
            })
            await trace_recorder.flush()
            
            # 记录 Token 使用量（后台任务，不阻塞）
            asyncio.create_task(token_monitor.record({
                "request_type": "recommend",
                "user_id": user_id,
                "message_id": message_id,
                "total_usage": result.usage,
                "latency_ms": result.duration_ms,
                "timestamp": int(time.time() * 1000),
            }))
            
            # 发送完成事件
            if on_event:
                await on_event({
                    "type": "complete",
                    "content": result.raw_output or "",
                    "usage": result.usage,
                })
            
            # 如果 review 通过且有 parsed plan，直接返回
            if result.plan:
                return {
                    "reply": result.raw_output or "",
                    "parsed": result.plan,
                }
            
            # review 未完全通过但有 raw_output，尝试最后一次修复解析
            if result.raw_output:
                from .nodes.validate import validate_with_repair
                try:
                    validate_result = validate_with_repair(result.raw_output)
                    return {
                        "reply": result.raw_output,
                        "parsed": validate_result["parsed"],
                    }
                except Exception:
                    pass
            
            raise ValueError("Agent 多次输出无效 JSON，请稍后重试")
                
        except Exception as e:
            error_msg = str(e)
            
            # 记录错误
            trace_recorder.add({
                "step": 1,
                "type": "error",
                "error": error_msg,
            })
            await trace_recorder.flush()
            
            # 发送错误事件
            if on_event:
                await on_event({
                    "type": "error",
                    "error": error_msg,
                })
            
            raise
