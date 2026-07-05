"""Agent Engine 模块。

LangGraph 多智能体编排引擎。
迁移自 Node.js 版本的 agentEngine.ts。
"""

import asyncio
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
from src.services.agent.trace_recorder import TraceRecorder
from src.services.agent.token_monitor import token_monitor
from src.services.agent.token_tracker import LLMContext


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
    ) -> dict:
        """多轮对话（使用 ChatGraph）。
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            conversation_id: 对话 ID（可选）
            on_event: 事件回调函数
            signal: 中止信号
            message_id: 消息 ID（用于 Trace 落表）
            
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
        
        # 构建系统提示词
        from .system_prompt import build_system_prompt
        system_prompt = build_system_prompt(
            user_preferences=preferences,
            conversation_summary=system_summary,
            conversation_recap=conversation_recap,
        )
        
        # 创建 TraceRecorder
        trace_recorder = TraceRecorder(message_id)
        step_counter = {"value": 1}
        
        # 构建 ChatGraph
        graph = build_chat_graph()
        
        # 构建配置
        config = {
            "configurable": {
                "trace_recorder": trace_recorder,
                "on_event": on_event,
                "signal": signal,
                "step_counter": step_counter,
                "llm": self.llm,
                "fallback_llm_config": self.fallback_llm_config,
                "system_prompt": system_prompt,
                "conversation_history": conversation_history,
            },
        }
        
        # 构建初始状态
        initial_state: PlannerState = {
            "user_id": user_id,
            "message": message,
            "city": "北京",  # router 节点会按消息内容覆盖
            "budget": None,
            "days": None,
            "departure_city": None,
            "user_preferences": preferences,
            "conversation_history": conversation_history,
            "research_bundle": {},
            "raw_output": None,
            "parsed": None,
            "usage": {"prompt": 0, "completion": 0, "total": 0, "cached": 0},
            "route": None,
            "errors": [],
        }
        
        try:
            # 执行 ChatGraph（设置 LLM 上下文，供 token_tracker callback 使用）
            with LLMContext(user_id=user_id, endpoint="chat"):
                result = await graph.ainvoke(initial_state, config=config)
            
            # 记录完成事件
            trace_recorder.add({
                "step": step_counter["value"],
                "type": "complete",
                "duration_ms": int((time.time() - start_time) * 1000),
            })
            await trace_recorder.flush()
            
            # 记录 Token 使用量（后台任务，不阻塞）
            asyncio.create_task(token_monitor.record({
                "request_type": "chat",
                "route": result.get("route"),
                "user_id": user_id,
                "conversation_id": conversation_id,
                "message_id": message_id,
                "total_usage": result.get("usage"),
                "latency_ms": int((time.time() - start_time) * 1000),
                "timestamp": int(time.time() * 1000),
            }))
            
            # 发送完成事件
            if on_event:
                await on_event({
                    "type": "complete",
                    "content": result.get("raw_output", ""),
                    "usage": result.get("usage"),
                })
            
            return {
                "reply": result.get("raw_output", ""),
                "conversation_id": conversation_id,
            }
            
        except Exception as e:
            error_msg = str(e)
            
            # 记录错误
            trace_recorder.add({
                "step": step_counter["value"],
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
        """行程推荐（使用 PlannerGraph）。
        
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
        await self.ensure_amap_tools()
        
        start_time = time.time()
        
        # 加载用户偏好
        preferences = await self._load_user_preferences(user_id)
        
        # 创建 TraceRecorder
        trace_recorder = TraceRecorder(message_id)
        step_counter = {"value": 1}
        
        # 构建输入消息
        input_message = (
            f"请为我规划{departure_city + '出发到' if departure_city else ''}"
            f"{city}{days}日游行程，预算{budget}元。"
        )
        
        # 构建 PlannerGraph
        graph = build_planner_graph()
        
        # 构建配置
        config = {
            "configurable": {
                "trace_recorder": trace_recorder,
                "on_event": on_event,
                "signal": None,
                "step_counter": step_counter,
                "llm": self.llm,
                "fallback_llm_config": self.fallback_llm_config,
            },
        }
        
        # 构建初始状态
        initial_state: PlannerState = {
            "user_id": user_id,
            "message": input_message,
            "city": city,
            "budget": budget,
            "days": days,
            "departure_city": departure_city,
            "user_preferences": preferences,
            "conversation_history": [],
            "research_bundle": {},
            "raw_output": None,
            "parsed": None,
            "usage": {"prompt": 0, "completion": 0, "total": 0, "cached": 0},
            "route": None,
            "errors": [],
        }
        
        try:
            # 执行 PlannerGraph（设置 LLM 上下文，供 token_tracker callback 使用）
            with LLMContext(user_id=user_id, endpoint="recommend"):
                result = await graph.ainvoke(initial_state, config=config)
            
            # 检查解析结果
            if result.get("parsed"):
                # 记录完成事件
                trace_recorder.add({
                    "step": step_counter["value"],
                    "type": "complete",
                    "duration_ms": int((time.time() - start_time) * 1000),
                })
                await trace_recorder.flush()
                
                # 记录 Token 使用量（后台任务，不阻塞）
                asyncio.create_task(token_monitor.record({
                    "request_type": "recommend",
                    "user_id": user_id,
                    "message_id": message_id,
                    "total_usage": result.get("usage"),
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "timestamp": int(time.time() * 1000),
                }))
                
                # 发送完成事件
                if on_event:
                    await on_event({
                        "type": "complete",
                        "content": result.get("raw_output", ""),
                        "usage": result.get("usage"),
                    })
                
                return {
                    "reply": result.get("raw_output", ""),
                    "parsed": result.get("parsed"),
                }
            
            # retry 后 raw_output 仍可能未过校验，二次校验一次
            from .validate import validate_with_repair
            try:
                validate_result = validate_with_repair(result.get("raw_output", ""))
                trace_recorder.add({
                    "step": step_counter["value"],
                    "type": "complete",
                    "duration_ms": int((time.time() - start_time) * 1000),
                })
                await trace_recorder.flush()
                
                # 记录 Token 使用量（后台任务，不阻塞）
                asyncio.create_task(token_monitor.record({
                    "request_type": "recommend",
                    "user_id": user_id,
                    "message_id": message_id,
                    "total_usage": result.get("usage"),
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "timestamp": int(time.time() * 1000),
                }))
                
                if on_event:
                    await on_event({
                        "type": "complete",
                        "content": result.get("raw_output", ""),
                        "usage": result.get("usage"),
                    })
                
                return {
                    "reply": result.get("raw_output", ""),
                    "parsed": validate_result["parsed"],
                }
            except Exception:
                raise ValueError("Agent 多次输出无效 JSON，请稍后重试")
                
        except Exception as e:
            error_msg = str(e)
            
            # 记录错误
            trace_recorder.add({
                "step": step_counter["value"],
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
