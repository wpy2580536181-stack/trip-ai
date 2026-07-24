"""SkillLoader：解析 SKILL.md 文件为 SkillCatalog + SkillSpec。

SKILL.md 结构（对齐 Anthropic Claude Code Skill 规范）：
    ---
    name: 行程规划
    description: "当用户提到行程、攻略、几日游时触发..."  # L1：常驻上下文
    ---

    # 标题（可选）

    正文内容                      # L2：被选中才整篇读入上下文

    references/scripts/assets     # L3：执行时按需加载的资源

目录扫描支持双路径：
- .claude/skills/<name>/SKILL.md  （Anthropic 标准，优先）
- src/services/agent/skills/skills/<name>/SKILL.md  （旧目录，向后兼容兜底）

为保持测试与运行环境零外部依赖，frontmatter 与分段均为轻量自写解析，
不引入 PyYAML。
"""

import os
import re
from typing import Optional

from .types import SkillCatalog, SkillSpec


def _parse_frontmatter(text: str):
    """解析 `--- ... ---` 包裹的 frontmatter，返回 (dict, body)。"""
    if not text.lstrip().startswith("---"):
        return {}, text
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.DOTALL)
    if not m:
        return {}, text
    fm, body = m.group(1), m.group(2)
    data: dict = {}
    for line in fm.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # 处理 YAML 折叠标量（>-）和多行描述
        if val.startswith(">-"):
            val = val[2:].strip()
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            data[key] = [
                x.strip().strip('"').strip("'")
                for x in inner.split(",")
                if x.strip()
            ]
        else:
            data[key] = val.strip('"').strip("'")
    return data, body


def _parse_sections(body: str) -> dict:
    """按 `## 标题` 切分正文，返回 {标题: 内容}。"""
    segments = re.split(r"^##\s+", body, flags=re.MULTILINE)
    sections: dict = {}
    for seg in segments:
        if not seg.strip():
            continue
        lines = seg.splitlines()
        title = lines[0].strip()
        content = "\n".join(lines[1:]).strip()
        sections[title] = content
    return sections


def parse_skill_file(path: str):
    """解析单个 SKILL.md，返回 (SkillCatalog | None, SkillSpec)。

    解析失败或缺少 name 时返回 (None, SkillSpec())。

    L2 层加载的是整篇 body 正文（而非仅结构化片段）；resources 收集正文中
    引用的 references/ scripts/ assets/ 相对路径，供 L3 执行时按需读取。
    """
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    fm, body = _parse_frontmatter(text)
    sections = _parse_sections(body)

    name = fm.get("name", "")
    if not name:
        return None, SkillSpec()

    catalog = SkillCatalog(
        name=name,
        description=fm.get("description", ""),
        tags=fm.get("tags", []),
        kind=fm.get("kind", "agent"),
    )
    spec = SkillSpec(
        trigger=sections.get("Trigger", ""),
        instructions=sections.get("Instructions", ""),
        input_schema=sections.get("Input Schema", ""),
        examples=sections.get("Examples", ""),
        body=body,  # 整篇正文作为 L2 激活层内容
        resources=_detect_resources(body),  # L3 按需加载的资源
    )
    return catalog, spec


# 资源引用检测：SKILL.md 中出现的 references/ scripts/ assets/ 路径
_RES_RE = re.compile(
    r"(?:references|scripts|assets)/[^\s)\]]+\."
    r"(?:md|py|txt|json|ya?ml|csv|png|jpe?g|svg|html)"
)


def _detect_resources(body: str) -> list:
    """从 SKILL.md 正文抽取被引用的 references/scripts/assets 相对路径。"""
    if not body:
        return []
    return sorted(set(_RES_RE.findall(body)))


def discover_skill_paths(skills_dirs: list[str] | str) -> list[str]:
    """递归扫描一个或多个目录下所有 SKILL.md（大小写不敏感）。

    Args:
        skills_dirs: 单个路径字符串或路径列表。支持 Anthropic 规范目录
            （.claude/skills/<name>/SKILL.md）和旧目录结构
            （src/.../skills/skills/<name>/SKILL.md）。
    """
    if isinstance(skills_dirs, str):
        skills_dirs = [skills_dirs]
    paths: list[str] = []
    for d in skills_dirs:
        if not os.path.isdir(d):
            continue
        for root, _dirs, files in os.walk(d):
            for fn in files:
                if fn.upper() == "SKILL.MD":
                    paths.append(os.path.join(root, fn))
    return sorted(paths)


def get_skill_dirs() -> list[str]:
    """返回所有技能目录路径列表。

    按优先级顺序：.claude/skills（Anthropic 标准） > src/.../skills/skills（旧目录）。
    优先目录存在时优先加载，旧目录作为兜底保证向后兼容。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    # here = .../src/services/agent/skills
    # project_root = .../trip-backend (4 levels up)
    project_root = os.path.normpath(os.path.join(here, "..", "..", "..", ".."))
    dirs: list[str] = []
    # Anthropic 标准目录
    claude_skills = os.path.join(project_root, ".claude", "skills")
    if os.path.isdir(claude_skills):
        dirs.append(claude_skills)
    # 旧目录（向后兼容）
    old_skills = os.path.join(here, "skills")
    if os.path.isdir(old_skills):
        dirs.append(old_skills)
    return dirs
