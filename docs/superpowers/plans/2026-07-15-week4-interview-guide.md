# Week 4 Plan — 项目讲解文档

> 配套 spec: `docs/superpowers/specs/2026-07-15-week4-interview-guide-design.md`
> 6 tasks, 4 批（1 线性 / 2 并行 / 1 线性 / 2 并行）

## Task 拆分

### 批次 1（线性，1 task）

#### Task 1: 写 `docs/interview-guide.md`（主讲解文档）
- **范围**: Part 1-4 全部内容
  - Part 1 — 项目总览（5 分钟）
  - Part 2 — 4 个亮点 STAR（30 分钟）
  - Part 3 — 10 个高频问题预演答案（30 分钟）
  - Part 4 — Trade-off 论述（10 分钟）
- **文件**: `docs/interview-guide.md`（目标 ≤ 1000 行）
- **风格**: 中英混合（技术术语英文 + 中文叙述）
- **要求**:
  - 每个 STAR 200 字，每个 trade-off 100-150 字
  - 10 个问题答案每个 150-200 字
  - 每个答案引用具体 commit SHA 或 file:line
  - 5 个数字在文档里出现 ≥ 2 次
  - 所有内部链接用相对路径
- **风险**: 内容可能过长（> 3000 行），需控制篇幅
- **耗时**: 30-40 分钟

### 批次 2（并行，2 tasks）

#### Task 2: 写 `docs/architecture-diagrams.md`（4 张 Mermaid）
- **范围**: 4 张图（每张 ≤30 行 Mermaid）
  - 系统架构图（flowchart）
  - Agent 时序图（sequenceDiagram）
  - 上下文数据流（flowchart）
  - 评估体系（flowchart）
- **文件**: `docs/architecture-diagrams.md`
- **验证**: 用 mermaid.live 或 GitHub 渲染测试
- **耗时**: 10 分钟

#### Task 3: 升级 `README.md`（加 2 个新章节）
- **范围**:
  - 在 ## Performance 之后，加 ## Architecture（3-5 句话 + 链接到 diagrams）
  - 加 ## Highlights（4 卡片，每卡片 1 句话 + 详细文档链接）
- **文件**: `README.md`
- **位置**: ## Performance 之后，## 项目结构 之前
- **耗时**: 10 分钟

### 批次 3（线性，1 task）

#### Task 4: 写 `docs/demo-script.md`（演示脚本）
- **范围**: 5-10 分钟演示的详细剧本
  - 0:00 - 0:30 项目介绍
  - 0:30 - 2:00 演示 chat 流式（前端）
  - 2:00 - 3:30 演示断点续传
  - 3:30 - 5:00 演示 admin trace
  - 5:00 - 6:30 演示反馈系统
  - 6:30 - 8:00 演示评估
  - 8:00 - 9:00 压测数字
  - 9:00 - 10:00 总结
- **风格**: 中英混合，分镜（screen 切镜 + 台词）
- **耗时**: 10 分钟

### 批次 4（并行，2 tasks）

#### Task 5: 写 `tasks/interview-checklist.md`（20 项 checklist）
- **范围**: 面试前 24 小时 checklist
- **分类**:
  - [ ] 文档准备（README / 4 亮点 / 10 问题 / 架构图）
  - [ ] 环境准备（docker 起来 / seed 完整 / .env.example）
  - [ ] 演示准备（chat / 断点续传 / admin / eval 跑通）
  - [ ] 知识准备（5 数字背熟 / 4 STAR / 10 答案）
  - [ ] 应急预案（服务器挂了 / 演示卡了 / 问题没准备）
- **耗时**: 5 分钟

#### Task 6: 最终验证
- **范围**:
  - mermaid 渲染（4 张图 GitHub 显示正常）
  - 链接检查（interview-guide.md → 其他文档）
  - 数字一致性（5 数字在 README + interview-guide + performance-benchmark 一致）
  - `pnpm test` 仍 9 passed / 6 failed（基线保持）
- **耗时**: 5 分钟

## 总耗时

- 批次 1: 30-40 分钟
- 批次 2: 10 分钟（并行）
- 批次 3: 10 分钟
- 批次 4: 5 分钟（并行）
- **总: ~55-70 分钟**（vs 串行 70-80 分钟）

## 关键约束

- 文档语言: 中英混合（技术术语英文 + 中文叙述）
- 架构图: 全 Mermaid（draw.io 不可行已确认）
- demo: 只写脚本不录视频
- 5 个数字在 ≥ 2 个文档出现
- 10 个问题答案每个都引用 commit SHA 或 file:line
- 不改任何代码

## 验证标准

- [ ] `docs/interview-guide.md` < 1000 行
- [ ] `docs/architecture-diagrams.md` 4 张 Mermaid 图（GitHub 渲染成功）
- [ ] README 新章节（## Architecture + ## Highlights）已加
- [ ] `docs/demo-script.md` 5-10 分钟详细分镜
- [ ] `tasks/interview-checklist.md` 20 项
- [ ] 5 数字在 ≥ 2 个文档出现
- [ ] `pnpm test` 基线 9 passed / 6 failed
- [ ] 所有内部链接相对路径
- [ ] 6 个 commit 全部清洁（无无关改动混入）
