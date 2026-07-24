"""SkillRegistry：三层渐进式披露的技能中枢。

- L1 目录层 list_catalog()：仅返回 SkillCatalog 轻量元信息，常用于注入系统提示词。
- L2 规格层 load_spec(name)：返回 SkillSpec（指令/触发/输入输出），技能「被选中」才调用。
- L3 实现层 execute(name, ctx, **kwargs)：构建披露轨迹 → 加载规格 → 调用 Skill.execute。
- load_from_directory()：扫描 skills/ 目录，把每个 SKILL.md 解析注册进来。

技能主体是 SKILL.md（声明式），而非写死的 Python 类；这让 skill 与 tool calling
形成清晰的层级：skill 是「流程说明」，tool 是「单步函数」。
"""

import os
import re
from typing import Any, Optional

from .types import SkillCatalog, SkillSpec, SkillContext, SkillResult, SkillLayer
from .base import Skill
from .loader import parse_skill_file, discover_skill_paths, get_skill_dirs


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    # ---------------- 注册 ----------------
    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    # ---------------- L1 目录层 ----------------
    def list_catalog(self) -> list[SkillCatalog]:
        return [s.catalog for s in self._skills.values()]

    def catalog_prompt(self, header: str = "# 可用技能") -> str:
        """渲染 L1 目录为提示词片段，供注入 planner/系统提示词。"""
        if not self._skills:
            return ""
        lines = [header, ""]
        for c in self.list_catalog():
            tag_str = ", ".join(c.tags) if c.tags else ""
            lines.append(
                f"- **{c.name}** [{c.kind}]：{c.description}（tags: {tag_str}）"
            )
        return "\n".join(lines)

    # ---------------- L2 规格层 ----------------
    def load_spec(self, name: str) -> Optional[SkillSpec]:
        s = self._skills.get(name)
        return s.load_spec() if s else None

    # ---------------- 粗选（兜底/无 LLM 时） ----------------
    def select(self, query: str) -> Optional[str]:
        """按 name/tags/Trigger 关键词做轻量粗选，返回最匹配技能名。

        作为「无 LLM 时」或「LLM 路由失败」的确定性兜底。匹配完整 description
        会造成技能名互相串味，故仅匹配 name/tags/Trigger 关键词。
        """
        q = (query or "").lower()
        if not q:
            return None
        best, best_score = None, 0
        for s in self._skills.values():
            score = 0
            if s.name.lower() in q:
                score += 3
            for t in s.catalog.tags:
                if t.lower() in q:
                    score += 2
            for kw in self._trigger_keywords(s.load_spec().trigger):
                if kw.lower() in q:
                    score += 1
            if score > best_score:
                best, best_score = s.name, score
        return best

    # ---------------- L1→L2 路由（LLM 驱动，文章标准） ----------------
    async def route_skill(self, query: str, llm: Any) -> Optional[str]:
        """用 LLM 从 L1 目录中选取最匹配的技能（匹配是 LLM 的推理行为）。

        文章标准：L1 目录常驻上下文，由 LLM 读 L1 描述自行判断何时加载 L2，
        而非用硬编码路由。返回技能名或 None。

        无 LLM 或解析失败时回退到 select() 关键字匹配。
        """
        if llm is None:
            return self.select(query)
        catalog = self.catalog_prompt(header="# 可用技能（L1 目录）")
        if not catalog:
            return None

        router_sys = (
            "你是技能路由器。下面是可用的技能目录（L1 目录，已常驻上下文）。\n"
            "根据用户请求，选择最合适的一个技能名称；若都不匹配，只回复 NONE。\n"
            "只回复技能名称或 NONE，不要任何解释。\n\n"
            f"{catalog}"
        )
        try:
            resp = await llm.ainvoke(
                [
                    {"role": "system", "content": router_sys},
                    {"role": "human", "content": f"用户请求：{query}"},
                ]
            )
            text = (getattr(resp, "content", None) or "").strip()
        except Exception:
            return self.select(query)

        if not text or text.upper() == "NONE":
            return None
        # 精确匹配技能名
        for s in self._skills.values():
            if s.name == text:
                return s.name
        # 容错：名称被包在句子里
        for s in self._skills.values():
            if s.name in text:
                return s.name
        # 仍不匹配 → 关键字兜底
        return self.select(query)

    @staticmethod
    def _trigger_keywords(trigger: str) -> list:
        """从 Trigger 文本抽取关键词（支持「a / b / c」或 a / b 形式）。"""
        if not trigger:
            return []
        m = re.search(r"包含[「\"](.+?)[」\"]", trigger)
        raw = m.group(1) if m else trigger
        kws = [k.strip().strip("/").strip() for k in re.split(r"[、/]", raw)]
        return [k for k in kws if k]

    # ---------------- L3 实现层 ----------------
    async def execute(
        self, name: str, ctx: SkillContext, **kwargs
    ) -> SkillResult:
        skill = self._skills.get(name)
        if not skill:
            return SkillResult(
                skill=name,
                ok=False,
                error=f"未注册技能: {name}",
                disclosure=list(ctx.disclosure),
            )
        # L1：已被选中（目录命中）
        ctx.disclosure.append(f"{SkillLayer.L1.value}:catalog:{name}")
        # L2：加载规格（指令）
        _spec = skill.load_spec()
        ctx.disclosure.append(f"{SkillLayer.L2.value}:spec:{name}")
        # L3：执行（指令驱动 LLM 编排）
        return await skill.execute(ctx, **kwargs)

    # ---------------- 批量加载 SKILL.md ----------------
    def load_from_directory(self, skills_dir: str) -> "SkillRegistry":
        for path in discover_skill_paths(skills_dir):
            cat, spec = parse_skill_file(path)
            if cat is not None:
                self.register(Skill(catalog=cat, spec=spec, path=path))
        return self


# ---------------- 全局单例 + 内置技能加载 ----------------
_REGISTRY = SkillRegistry()


def get_skill_registry() -> SkillRegistry:
    return _REGISTRY


def load_builtin_skills(
    registry: Optional[SkillRegistry] = None,
) -> SkillRegistry:
    """加载内置技能。

    优先从 .claude/skills/（Anthropic 标准目录）加载；
    若不存在则回退到旧目录 src/.../skills/skills/ 保证向后兼容。
    幂等：重复调用会用同名覆盖。
    """
    reg = registry or get_skill_registry()
    for skills_dir in get_skill_dirs():
        reg.load_from_directory(skills_dir)
    return reg
