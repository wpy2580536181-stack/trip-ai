"""Skill 运行时对象。

一个 Skill 就是一份 SKILL.md 解析后的产物：
- L1 catalog：构造即持有（轻量元信息，常驻上下文）
- L2 spec：load_spec() 返回（整篇正文 body，被「选中」才读入）
- L3 execute：被调用才执行——把整篇 SKILL.md 正文交给 LLM，由 LLM 借助
  ctx.tools 做 tool calling 自行编排；执行中引用的 references/scripts/assets
  作为 L3 第三层按需读入。**不写死代码流程**。这正是 Skill 与裸 tool calling
  的本质区别：Skill 是「给 LLM 走的流程说明」。
"""

import os
from typing import Optional

from .types import SkillCatalog, SkillSpec, SkillContext, SkillResult, SkillLayer


class Skill:
    """由 SKILL.md 解析而来的技能运行时对象。"""

    def __init__(
        self,
        catalog: SkillCatalog,
        spec: SkillSpec,
        path: str = "",
    ) -> None:
        self.catalog = catalog
        self._spec = spec
        self.path = path  # SKILL.md 路径，用于解析同目录下的 L3 资源

    @property
    def name(self) -> str:
        return self.catalog.name

    # ---- L2：规格层（被选中才读取） ----
    def load_spec(self) -> SkillSpec:
        return self._spec

    # ---- L3：资源层（执行时按需读取） ----
    def load_resources(self) -> tuple[str, list]:
        """读取 SKILL.md 引用的 references/scripts/assets 文件内容。

        Returns:
            (拼接后的资源文本, 实际成功加载的相对路径列表)
        """
        if not self.path or not self._spec.resources:
            return "", []
        base = os.path.dirname(self.path)
        parts: list = []
        loaded: list = []
        for rel in self._spec.resources:
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

    # ---- 执行层（L2 正文注入 + L3 资源按需加载） ----
    async def execute(self, ctx: SkillContext, **kwargs) -> SkillResult:
        """指令驱动执行：把整篇 SKILL.md（L2）交给 LLM，按需注入 L3 资源。

        LLM 借助 ctx.tools 进行 tool calling，自行编排完成技能目标。
        本方法只负责「装配提示词 + 调用 LLM」，具体步骤写在 SKILL.md 里。
        """
        if ctx.llm is None:
            return SkillResult(
                skill=self.name,
                ok=False,
                error="SkillContext.llm 未注入，无法执行指令驱动技能",
                disclosure=list(ctx.disclosure),
            )

        spec = self._spec
        # L2 激活层：加载整篇 SKILL.md 正文（文章标准，而非仅结构化片段）
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

        # L3 执行层：按需加载 references/scripts/assets（未被引用则不进上下文）
        res_text, res_paths = self.load_resources()
        l3_tag = f"{SkillLayer.L3.value}:execute:{self.name}"
        if res_text:
            system += f"\n## 参考资料（L3 按需加载）\n{res_text}\n"
            if res_paths:
                l3_tag += f":resources={','.join(res_paths)}"

        human = (
            f"用户原始输入：{ctx.user_input or '(无)'}\n"
            f"技能入参：{kwargs}"
        )

        llm = ctx.llm
        if ctx.tools:
            llm = ctx.llm.bind_tools(ctx.tools)

        resp = await llm.ainvoke(
            [
                {"role": "system", "content": system},
                {"role": "human", "content": human},
            ]
        )
        content = getattr(resp, "content", str(resp))
        ctx.disclosure.append(l3_tag)
        return SkillResult(
            skill=self.name, ok=True, content=content, disclosure=list(ctx.disclosure)
        )
