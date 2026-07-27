"""Agent 基类模块。

定义 BaseAgent 抽象基类，每个 Agent 拥有：
- 独立 system_prompt
- 独立 tools 列表
- 独立 LLM 实例（可用不同 temperature）
- 独立 Input/Output schema

Agent 之间不共享 State。
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage

from src.services.agent.types import TokenUsage

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    """Agent 输入基类。每个 Agent 有自己的 schema 继承此类。"""
    pass


@dataclass
class AgentOutput:
    """Agent 输出基类。"""

    agent_name: str
    """Agent 名称"""

    result: Any = None
    """Agent 执行结果（类型由具体 Agent 定义）"""

    usage: TokenUsage = field(default_factory=lambda: {
        "prompt": 0, "completion": 0, "total": 0, "cached": 0,
    })
    """本次执行的 Token 消耗"""

    duration_ms: int = 0
    """执行耗时（毫秒）"""

    error: Optional[str] = None
    """错误信息（成功时为 None）"""


def extract_usage_from_message(message: AIMessage) -> TokenUsage:
    """从 LLM AIMessage 中提取 Token 使用情况。

    兼容 usage_metadata 和 response_metadata.usage 两种来源。

    Args:
        message: LangChain AIMessage

    Returns:
        TokenUsage 字典
    """
    usage: TokenUsage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}

    # 尝试从 usage_metadata 提取
    um = getattr(message, "usage_metadata", None)
    if um:
        usage["prompt"] = um.get("input_tokens", 0)
        usage["completion"] = um.get("output_tokens", 0)
        usage["total"] = um.get("total_tokens", usage["prompt"] + usage["completion"])
        input_details = um.get("input_token_details", {})
        usage["cached"] = input_details.get("cache_read", 0) if isinstance(input_details, dict) else 0
        return usage

    # 尝试从 response_metadata.usage 提取
    rm = getattr(message, "response_metadata", None)
    if rm and isinstance(rm, dict):
        ru = rm.get("usage", {})
        if ru and isinstance(ru, dict):
            usage["prompt"] = ru.get("prompt_tokens", 0)
            usage["completion"] = ru.get("completion_tokens", 0)
            usage["total"] = ru.get("total_tokens", usage["prompt"] + usage["completion"])
            prompt_details = ru.get("prompt_tokens_details", {})
            if prompt_details and isinstance(prompt_details, dict):
                usage["cached"] = prompt_details.get("cached_tokens", 0)
            return usage

    return usage


class BaseAgent(ABC):
    """Agent 抽象基类。

    每个 Agent 拥有独立的上下文（system_prompt + tools + LLM），
    通过 run() 方法独立执行，输入输出通过明确的 schema 定义。
    """

    name: str = "base"
    """Agent 名称标识"""

    def __init__(
        self,
        llm: ChatOpenAI,
        tools: Optional[list] = None,
        system_prompt: str = "",
    ):
        """初始化 Agent。

        Args:
            llm: ChatOpenAI 实例（每个 Agent 可用不同模型/温度）
            tools: 该 Agent 专属的工具列表
            system_prompt: 该 Agent 的系统提示词
        """
        self.llm = llm
        self.tools = tools or []
        self.system_prompt = system_prompt

    @abstractmethod
    async def run(self, input: AgentInput) -> AgentOutput:
        """执行 Agent 逻辑。子类必须实现。

        Args:
            input: Agent 输入（具体类型由子类定义）

        Returns:
            AgentOutput 包含结果和 Token 消耗
        """
        ...

    async def _invoke_llm(
        self,
        messages: list[dict],
        timeout_s: float = 60.0,
    ) -> tuple[str, TokenUsage, AIMessage]:
        """调用 LLM（带工具绑定和超时）。

        Args:
            messages: 消息列表 [{"role": "system"/"human", "content": "..."}]
            timeout_s: 超时秒数

        Returns:
            (content, usage, raw_message) 元组
        """
        import asyncio

        llm = self.llm
        if self.tools:
            llm = llm.bind_tools(self.tools)

        _t0 = time.time()
        try:
            result = await asyncio.wait_for(
                llm.ainvoke(messages),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"{self.name} LLM 调用超时（{timeout_s}秒）"
            )

        duration_ms = int((time.time() - _t0) * 1000)

        # 提取内容和 usage
        if isinstance(result, AIMessage):
            content = result.content if isinstance(result.content, str) else ""
            usage = extract_usage_from_message(result)
        else:
            content = str(result)
            usage = {"prompt": 0, "completion": 0, "total": 0, "cached": 0}
            result = AIMessage(content=content)

        logger.info(
            "%s|llm duration=%dms content_len=%d prompt_tokens=%d completion_tokens=%d",
            self.name, duration_ms, len(content),
            usage.get("prompt", 0), usage.get("completion", 0),
        )

        return content, usage, result
