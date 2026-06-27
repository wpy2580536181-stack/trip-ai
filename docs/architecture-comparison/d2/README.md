# D2 架构图示例 (D2 Architecture Diagrams)

> 4 张 D2 图，对应 [`docs/architecture-diagrams.md`](../architecture-diagrams.md) 的 Mermaid 源。
> 本目录用于横向对比 D2 vs Mermaid 的视觉与维护体验。

## 什么是 D2

[D2](https://d2lang.com) 是 Terrastruct 出品的一款现代图表脚本语言。

- 声明式语法，类似 Mermaid 但更接近"代码"
- 自动布局（默认 dagre，可选 ELK）
- 主题丰富（官方 + 社区 80+ 主题）
- 原生支持：流程图、序列图、类图、架构图
- 标签支持 Markdown / LaTeX
- 可生成 SVG / PNG / PDF

## 安装

```bash
# macOS
brew install d2

# 或一键脚本
curl -fsSL https://d2lang.com/install.sh | sh -s --
```

## 渲染

```bash
# 4 张图
d2 system-architecture.d2  system-architecture.svg
d2 agent-sequence.d2       agent-sequence.svg
d2 context-data-flow.d2    context-data-flow.svg
d2 evaluation-system.d2    evaluation-system.svg

# 批量
for f in *.d2; do d2 "$f" "${f%.d2}.svg"; done

# 带主题（推荐）
d2 --theme=200 system-architecture.d2 out.svg      # 深色
d2 --theme=GrapeBat system-architecture.d2 out.svg # 暖色
```

## 4 张图概览

| # | 文件 | 主题 |
|---|------|------|
| 1 | `system-architecture.d2` | 系统整体架构（前端 / 后端 / DB / LLM） |
| 2 | `agent-sequence.d2` | Agent 执行时序（17 步 SSE 流） |
| 3 | `context-data-flow.d2` | 上下文压缩数据流（3 路决策） |
| 4 | `evaluation-system.d2` | 评估体系（fixture → 评估 → 反馈） |

## D2 vs Mermaid 对比

| 维度 | D2 | Mermaid |
|------|----|----|
| GitHub 原生渲染 | ❌ 需本地 / CI 渲染 | ✅ 提交即看 |
| 语法可读性 | ✅ 接近代码 | 一般（缩进敏感） |
| 形状库 | ✅ 丰富（cylinder / cloud / package / hexagon / page） | 有限 |
| 颜色/样式 | ✅ 节点级 + 连线级 | 全局 theme |
| 主题 | ✅ 80+ 官方主题 | 5 个左右 |
| 序列图 | ✅ 原生支持 | ✅ |
| 自动布局 | ✅ dagre / ELK | dagre |
| 复杂图性能 | ✅ 快 | 节点多时变慢 |
| 嵌入文档 | 需生成 SVG 提交 | 直接 `mermaid` 代码块 |
| 学习曲线 | 低 | 低 |

**结论：**
- 文档仓库首选 **Mermaid**（GitHub 直接渲染，无需 CI）
- 复杂架构图、对外分享、PPT 配图首选 **D2**（视觉更精致、形状更多）

## D2 特有优势（Mermaid 没有的）

1. **丰富的形状语义** — `cylinder`（数据库）、`cloud`（外部服务）、`package`（模块）、`hexagon`（核心）、`page`（文档）、`person`（用户）等等，让"代码即图表"更准确。
2. **节点级 + 连线级样式** — 每个节点和边都可以独立配置 `fill` / `stroke` / `stroke-width` / `font-color` / `bold`，Mermaid 通常只能依赖全局 theme。
3. **ELK 布局** — 比 dagre 更智能，可减少连线交叉。
4. **图标库 (icons)** — 可直接引用 `aws.*` / `gcp.*` / `azure.*` / `kafka` / `redis` 等图标，无需手画 logo。
5. **变量 & 函数** — 支持 `vars` 块定义全局颜色变量，方便主题切换。

## 文件清单

```
docs/architecture-comparison/d2/
├── README.md                   # 本文件
├── system-architecture.d2      # 1. 系统架构
├── agent-sequence.d2           # 2. Agent 时序
├── context-data-flow.d2        # 3. 上下文数据流
└── evaluation-system.d2        # 4. 评估体系
```
