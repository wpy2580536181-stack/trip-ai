"""Skills 包：SKILL.md 驱动的技能体系，三层渐进式披露。

- 技能主体是一份 SKILL.md（声明式：frontmatter + Trigger/Instructions/Input/Examples）
- SkillLoader 负责解析 SKILL.md → SkillCatalog(L1) + SkillSpec(L2)
- SkillRegistry 负责 L1 目录 / L2 规格 / L3 执行，以及批量加载与选择
- 执行时把 L2 的 instructions 交给 LLM，由 LLM 借助 tool calling 自行编排

内置技能位于 ./skills/<name>/SKILL.md，由 load_builtin_skills() 加载。
"""

from .types import (
    SkillLayer,
    SkillCatalog,
    SkillSpec,
    SkillContext,
    SkillResult,
)
from .base import Skill
from .registry import (
    SkillRegistry,
    get_skill_registry,
    load_builtin_skills,
)
from .loader import parse_skill_file, discover_skill_paths, get_skill_dirs
from .runtime import build_skill_context, run_selected_skill

__all__ = [
    "SkillLayer",
    "SkillCatalog",
    "SkillSpec",
    "SkillContext",
    "SkillResult",
    "Skill",
    "SkillRegistry",
    "get_skill_registry",
    "load_builtin_skills",
    "parse_skill_file",
    "discover_skill_paths",
    "get_skill_dirs",
    "build_skill_context",
    "run_selected_skill",
]
