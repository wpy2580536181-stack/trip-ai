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
    ):
        """初始化 ChatAgent。

        Args:
            llm: LLM 实例（streaming=True）
            on_event: SSE 事件回调
            system_prompt: 系统提示词（由 agent_engine 构建）
        """
        # 工具在 run() 时动态绑定（因为需要延迟加载）
        super().__init__(llm=llm, tools=[], system_prompt=system_prompt)
        self.on_event = on_event

    async def run(
        self,
        message: str,
        conversation_history: Optional[list] = None,
        system_prompt: Optional[str] = None,
        trip_context: Optional[str] = None,
    ) -> AgentOutput:
        """执行对话。

        Args:
            message: 用户当前消息
            conversation_history: 多轮对话历史（LangChain 消息列表）
            system_prompt: 系统提示词（覆盖初始化时的）
            trip_context: 用户已有行程摘要（注入 system prompt）

        Returns:
            AgentOutput，result 为回复文本
        """
        _t0 = time.time()

        # 构建 system prompt
        sys_prompt = system_prompt or self.system_prompt
        if trip_context:
            sys_prompt += f"\n\n# 用户当前行程\n{trip_context}\n"

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

        # 调用 LLM（带工具绑定）
        self.tools = tools
        try:
            content, usage, raw_msg = await self._invoke_llm(
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
                    plan_result = await self._escalate_plan(tc_args)
                    if plan_result:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=plan_result,
                            usage=usage,
                            duration_ms=duration_ms,
                        )

                elif tc_name == "trigger_modify":
                    # 升级为 Orchestrator.modify()
                    modify_result = await self._escalate_modify(tc_args)
                    if modify_result:
                        duration_ms = int((time.time() - _t0) * 1000)
                        return AgentOutput(
                            agent_name=self.name,
                            result=modify_result,
                            usage=usage,
                            duration_ms=duration_ms,
                        )

        # 流式发送 chunk 事件
        if self.on_event and content:
            await self.on_event({"type": "chunk", "content": content})

        duration_ms = int((time.time() - _t0) * 1000)
        return AgentOutput(
            agent_name=self.name,
            result=content,
            usage=usage,
            duration_ms=duration_ms,
        )

    async def _get_tools(self) -> list:
        """获取 ChatAgent 的工具列表（延迟加载）。

        工具列表：
        - retrieve_knowledge（RAG 检索）
        - search_hotels（酒店搜索）
        - trigger_plan（升级：触发全量规划）
        - trigger_modify（升级：触发局部修改）
        - amap_weather（MCP 天气，如果可用）
        """
        from src.services.agent.tools import retrieve_knowledge_tool, search_hotels_tool
        from src.services.agent.agents.trigger_tools import trigger_plan, trigger_modify

        tools = [retrieve_knowledge_tool, search_hotels_tool, trigger_plan, trigger_modify]

        # 尝试加载高德 MCP 天气工具
        try:
            from src.services.mcp.amap_client import get_amap_tools
            amap_tools = await get_amap_tools()
            if amap_tools:
                tools.extend(amap_tools[:3])
        except Exception:
            pass

        return tools

    async def _escalate_plan(self, args: dict) -> Optional[str]:
        """升级为 Orchestrator.plan()。"""
        try:
            from src.services.agent.orchestrator import Orchestrator
            from src.services.agent.schemas import PlanRequest

            orchestrator = Orchestrator(llm=self.llm, on_event=self.on_event)
            request = PlanRequest(
                user_id=0,  # ChatAgent 不持有 user_id，由上层传入
                city=args.get("city", ""),
                days=args.get("days", 3),
                budget=args.get("budget", 5000),
                departure_city=args.get("departure_city") or None,
                message=f"规划{args.get('city', '')}{args.get('days', 3)}日游",
            )
            result = await orchestrator.plan(request)
            if result.plan:
                import json
                return json.dumps(result.plan, ensure_ascii=False)
            return result.raw_output
        except Exception as e:
            logger.error("chat_agent|escalate_plan failed: %s", e)
            return None

    async def _escalate_modify(self, args: dict) -> Optional[str]:
        """升级为 Orchestrator.modify()。"""
        try:
            modify_request = args.get("modify_request", "")
            # Phase 4: 需要 trip_context 才能修改
            # 当前返回提示信息
            return f"行程修改功能即将上线。您的修改要求已记录：{modify_request}"
        except Exception as e:
            logger.error("chat_agent|escalate_modify failed: %s", e)
            return None
