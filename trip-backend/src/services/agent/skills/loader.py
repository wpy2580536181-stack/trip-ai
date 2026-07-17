"""SkillLoader：解析 SKILL.md 文件为 SkillCatalog + SkillSpec。

SKILL.md 结构（对齐"渐进式加载"标准，frontmatter 常驻 L1，正文整篇为 L2，
references/scripts/assets 为 L3 按需加载）：
    ---
    name: 行程规划
    description: ...            # L1：会话启动即常驻系统提示词
    tags: [itinerary, planning, 行程, 攻略]
    kind: agent                # agent | tool
    ---

    # 标题（可选）

    ## Trigger
    ...

    ## Instructions
    ...                        # L2：被选中才整篇读入上下文

    ## Input Schema
    ```json
    {...}
    ```

    ## Examples
    ...

    ## 注意事项
    ...                        # 允许自由增删段落，结构不写死

    # 执行时引用资源（L3 按需加载，未被引用则不进上下文）
    参考 references/itinerary-notes.md

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


def discover_skill_paths(skills_dir: str) -> list:
    """递归扫描目录下所有 SKILL.md（大小写不敏感）。"""
    if not os.path.isdir(skills_dir):
        return []
    paths: list = []
    for root, _dirs, files in os.walk(skills_dir):
        for fn in files:
            if fn.upper() == "SKILL.MD":
                paths.append(os.path.join(root, fn))
    return sorted(paths)
