"""Skill 运行时对象。

一个 Skill 就是一份 SKILL.md 解析后的产物：
- L1 catalog：构造即持有（轻量元信息，常驻上下文）
- L2 spec：load_spec() 时才从磁盘读取（lazy-load，被「选中」才读入）
- L3 execute：被调用才执行——把整篇 SKILL.md 正文交给 LLM，由 LLM 借助
  ctx.tools 做 tool calling 自行编排；执行中引用的 references/scripts/assets
  作为 L3 第三层按需读入。**不写死代码流程**。这正是 Skill 与裸 tool calling
  的本质区别：Skill 是「给 LLM 走的流程说明」。
"""

import os
from typing import Optional

from langchain_core.messages import ToolMessage

from .types import SkillCatalog, SkillSpec, SkillContext, SkillResult, SkillLayer


# 多轮 tool calling 最大迭代次数，防止死循环
MAX_SKILL_ITERATIONS = 10


class Skill:
    """由 SKILL.md 解析而来的技能运行时对象。"""

    def __init__(
        self,
        catalog: SkillCatalog,
        path: str = "",
    ) -> None:
        self.catalog = catalog
        self.path = path  # SKILL.md 路径，用于解析同目录下的 L3 资源
        self._spec: Optional[SkillSpec] = None  # lazy-load

    @property
    def name(self) -> str:
        return self.catalog.name

    # ---- L2：规格层（被选中才读取，lazy-load） ----
    def load_spec(self) -> SkillSpec:
        """L2 按需加载：首次调用时才从磁盘解析 SKILL.md 正文。"""
        if self._spec is None:
            from .loader import parse_skill_file
            _, spec = parse_skill_file(self.path)
            self._spec = spec
        return self._spec

    # ---- L3：资源层（执行时按需读取） ----
    def load_resources(self) -> tuple[str, list]:
        """读取 SKILL.md 引用的 references/scripts/assets 文件内容。

        Returns:
            (拼接后的资源文本, 实际成功加载的相对路径列表)
        """
        spec = self.load_spec()
        if not self.path or not spec.resources:
            return "", []
        base = os.path.dirname(self.path)
        parts: list = []
        loaded: list = []
        for rel in spec.resources:
            fp = os.path.join(base, rel)
            if os.path.isfile(fp):
                try:
                    with open(fp, "r", encoding="utf-8") as f:
                        content = f.read()
                    parts.append(f"### {rel}\n{content}")
                    loaded.append(rel)
                except Exception:
                    continue
        return "\n\n".join(parts), loaded

    # ---- 内部：拼装系统提示词（L2 正文 + L3 资源） ----
    def _build_system_prompt(self, spec: SkillSpec) -> tuple[str, str]:
        """拼装执行用系统提示词。

        Returns:
            (system_prompt, l3_tag)
        """
        # L2 激活层：加载整篇 SKILL.md 正文
        l2 = spec.body or (
            f"## 触发条件\n{spec.trigger}\n\n"
            f"## 执行指令\n{spec.instructions}\n\n"
            f"## 输入契约\n{spec.input_schema}"
        )
        system = (
            f"你正在执行技能「{self.name}」（类型：{self.catalog.kind}）。\n"
            f"请严格遵循下面的技能说明，并使用可用工具完成任务。\n\n"
            f"{l2}\n"
        )

        # L3 执行层：按需加载 references/scripts/assets
        res_text, res_paths = self.load_resources()
        l3_tag = f"{SkillLayer.L3.value}:execute:{self.name}"
        if res_text:
            system += f"\n## 参考资料（L3 按需加载）\n{res_text}\n"
            if res_paths:
                l3_tag += f":resources={','.join(res_paths)}"

        return system, l3_tag

    # ---- 执行层（多轮 tool calling agent loop） ----
    async def execute(self, ctx: SkillContext, **kwargs) -> SkillResult:
        """指令驱动执行：把整篇 SKILL.md（L2）交给 LLM，按需注入 L3 资源。

        LLM 借助 ctx.tools 进行多轮 tool calling，自行编排完成技能目标。
        本方法只负责「装配提示词 + agent loop 调用 LLM + 执行 tool calls」，
        具体步骤写在 SKILL.md 里。
        """
        if ctx.llm is None:
            return SkillResult(
                skill=self.name,
                ok=False,
                error="SkillContext.llm 未注入，无法执行指令驱动技能",
                disclosure=list(ctx.disclosure),
            )

        spec = self.load_spec()
        system, l3_tag = self._build_system_prompt(spec)

        messages: list = [
            {"role": "system", "content": system},
            {"role": "human", "content": (
                f"用户原始输入：{ctx.user_input or '(无)'}\n"
                f"技能入参：{kwargs}"
            )},
        ]

        llm = ctx.llm.bind_tools(ctx.tools) if ctx.tools else ctx.llm
        tool_map = {t.name: t for t in ctx.tools} if ctx.tools else {}

        for _ in range(MAX_SKILL_ITERATIONS):
            resp = await llm.ainvoke(messages)
            tool_calls = getattr(resp, "tool_calls", None)
            if not tool_calls:
                # 最终回答
                content = getattr(resp, "content", str(resp))
                ctx.disclosure.append(l3_tag)
                return SkillResult(
                    skill=self.name, ok=True, content=content,
                    disclosure=list(ctx.disclosure),
                )

            # 执行 tool calls 并追加结果到消息历史
            messages.append(resp)
            for tc in tool_calls:
                tool_fn = tool_map.get(tc["name"])
                if tool_fn:
                    try:
                        result = await tool_fn.ainvoke(tc["args"])
                    except Exception as e:
                        result = f"Tool error: {e}"
                else:
                    result = f"Error: unknown tool {tc['name']}"
                messages.append(ToolMessage(
                    content=str(result), tool_call_id=tc["id"]
                ))

        # 超过最大轮次
        ctx.disclosure.append(l3_tag)
        return SkillResult(
            skill=self.name, ok=False,
            error=f"超过最大执行轮次 ({MAX_SKILL_ITERATIONS})",
            disclosure=list(ctx.disclosure),
        )
