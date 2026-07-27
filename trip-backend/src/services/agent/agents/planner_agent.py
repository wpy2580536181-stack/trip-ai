"""PlannerAgent 模块。

真 Agent：基于 ResearchBundle 候选池创造性生成结构化行程 JSON。
核心特征：
- 封闭世界约束：只能使用候选池中的景点（prompt 硬约束）
- 支持 feedback 输入（review 不通过时带修改意见重跑）
- 独立上下文，不共享 Research 的对话历史
"""

import json
import logging
import time
from typing import Optional

from langchain_openai import ChatOpenAI

from src.services.agent.agents.base_agent import BaseAgent, AgentOutput
from src.services.agent.schemas import PlannerInput, ResearchBundle
from src.services.agent.types import TokenUsage

logger = logging.getLogger(__name__)

# 超时配置
PLAN_TIMEOUT_S = 60.0
RETRY_TIMEOUT_S = 30.0


class PlannerAgent(BaseAgent):
    """Planner Agent：基于候选池生成结构化行程。

    独立上下文：每次调用都是全新的 system_prompt + user_message，
    不保留前次对话历史。重试时通过 feedback 字段注入修改意见。
    """

    name = "planner"

    def __init__(self, llm: ChatOpenAI, fallback_llm: Optional[ChatOpenAI] = None):
        """初始化 PlannerAgent。

        Args:
            llm: 主 LLM 实例
            fallback_llm: 备用 LLM（主 LLM 失败时切换）
        """
        super().__init__(llm=llm, tools=[], system_prompt="")
        self.fallback_llm = fallback_llm

    async def run(self, input: PlannerInput) -> AgentOutput:
        """生成行程规划。

        Args:
            input: PlannerInput 包含候选池、约束、feedback 等

        Returns:
            AgentOutput，result 为 raw_output 字符串（JSON）
        """
        _t0 = time.time()

        # 构建 system prompt
        system_prompt = self._build_system_prompt(input)

        # 构建 user message
        user_message = self._build_user_message(input)

        # 调用 LLM
        timeout = RETRY_TIMEOUT_S if input.feedback else PLAN_TIMEOUT_S
        try:
            content, usage, _ = await self._invoke_llm(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "human", "content": user_message},
                ],
                timeout_s=timeout,
            )
        except Exception as e:
            # 主 LLM 失败，尝试备用
            if self.fallback_llm:
                logger.warning("planner_agent|primary_failed, trying fallback: %s", e)
                original_llm = self.llm
                self.llm = self.fallback_llm
                try:
                    content, usage, _ = await self._invoke_llm(
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "human", "content": user_message},
                        ],
                        timeout_s=timeout,
                    )
                finally:
                    self.llm = original_llm
            else:
                return AgentOutput(
                    agent_name=self.name,
                    error=str(e),
                    duration_ms=int((time.time() - _t0) * 1000),
                )

        duration_ms = int((time.time() - _t0) * 1000)
        logger.info(
            "planner_agent|done city=%s days=%d duration=%dms content_len=%d feedback=%s",
            input.city, input.days, duration_ms, len(content), bool(input.feedback),
        )

        return AgentOutput(
            agent_name=self.name,
            result=content,
            usage=usage,
            duration_ms=duration_ms,
        )

    def _build_system_prompt(self, input: PlannerInput) -> str:
        """构建 Planner 的 system prompt。

        包含：角色定义 + 封闭世界约束 + 输出格式 + 候选池数据。
        复用现有 planner_prompt.build_planner_prompt 的核心逻辑。
        """
        from src.services.agent.planner_prompt import build_planner_prompt

        prompt = build_planner_prompt(
            city=input.city,
            budget=input.budget,
            days=input.days,
            departure_city=input.departure_city,
            user_preferences=input.preferences,
            research_bundle=input.bundle.to_dict() if input.bundle else {},
        )

        # 封闭世界约束（候选池中的景点名列表）
        if input.bundle:
            spot_names = input.bundle.all_spot_names()
            if spot_names:
                names_str = "、".join(list(spot_names)[:30])  # 最多列 30 个
                prompt += (
                    f"\n\n# 封闭世界约束（CRITICAL）\n"
                    f"你只能使用以下候选景点，不得编造不存在的景点：\n"
                    f"{names_str}\n"
                    f"如果候选池中没有合适的景点，可以基于通用知识补充，但必须在 description 中标注'参考'。\n"
                )

        # 修改意见注入（重试时）
        if input.feedback:
            prompt += (
                f"\n\n# 修改要求（CRITICAL — 必须响应以下所有问题）\n"
                f"{input.feedback}\n"
            )

        return prompt

    def _build_user_message(self, input: PlannerInput) -> str:
        """构建 user message。"""
        if input.message:
            return input.message

        dep = f"{input.departure_city}出发到" if input.departure_city else ""
        msg = f"请为我规划{dep}{input.city}{input.days}日游行程，预算{input.budget}元。"

        if input.feedback:
            msg += f"\n\n注意：上次生成的行程存在以下问题，请修正：\n{input.feedback}"

        return msg
