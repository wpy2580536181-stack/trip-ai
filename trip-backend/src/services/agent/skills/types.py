"""Skills 类型定义（三层渐进式披露）。

- L1 目录层 (SkillCatalog)：仅轻量元信息，常驻上下文，供 planner/router 选择。
- L2 规格层 (SkillSpec)：触发条件 / 执行指令 / 输入契约 / 示例，技能「被选中」才加载。
- L3 实现层：把 L2 的 instructions 交给 LLM，由 LLM 借助 tool calling 自行编排执行。

技能主体是一份 SKILL.md（见 skills/skills/<name>/SKILL.md），由 SkillLoader 解析为
SkillCatalog + SkillSpec；不做写死的代码编排。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class SkillLayer(str, Enum):
    """渐进式披露的三层。"""

    L1 = "L1"  # 目录层：name/description/tags/kind，常驻上下文
    L2 = "L2"  # 规格层：trigger/instructions/input_schema/examples
    L3 = "L3"  # 实现层：被调用执行


@dataclass
class SkillCatalog:
    """L1 目录：常驻上下文的轻量元信息，不含指令本身。"""

    name: str
    description: str
    tags: list[str] = field(default_factory=list)
    kind: str = "agent"  # agent | tool


@dataclass
class SkillSpec:
    """L2 规格：技能被「选中」后才读取的详细定义。

    - trigger/instructions/input_schema/examples：结构化字段（供程序化读取）。
    - body：整篇 SKILL.md 正文（L2 激活层加载给 LLM 的就是它，符合文章标准
      "L2 = 整篇 SKILL.md"而非只取结构化片段）。
    - resources：SKILL.md 中引用的 references/scripts/assets 相对路径，
      L3 执行时按需读取（渐进式披露的第三层）。
    """

    trigger: str = ""
    instructions: str = ""
    input_schema: str = ""
    examples: str = ""
    body: str = ""  # 整篇 SKILL.md 正文（L2 激活层内容）
    resources: list = field(default_factory=list)  # L3 按需加载的资源相对路径


@dataclass
class SkillContext:
    """L3 执行上下文，由调用方（AgentEngine）注入。"""

    llm: Any = None
    tools: list = field(default_factory=list)
    registry: Any = None
    user_input: str = ""
    disclosure: list[str] = field(default_factory=list)


@dataclass
class SkillResult:
    """技能执行结果，附带经历的层级披露轨迹（便于评估/可观测）。"""

    skill: str
    ok: bool = True
    content: str = ""
    disclosure: list[str] = field(default_factory=list)
    error: Optional[str] = None
