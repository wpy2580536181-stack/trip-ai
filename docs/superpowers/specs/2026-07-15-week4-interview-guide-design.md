# Week 4 Spec — 项目讲解文档

> 配套 `docs/interview-plan.md` 亮点 4
> 目标日期：2026-07-22

## 目标

把 4 周亮点（断点续传 / 可视化 trace / 反馈闭环 / 压测）组装成面试可用的讲解文档体系，让候选人在 1.5-2 小时内能讲完整个项目，10 个高频问题有预演答案。

## 现状

- ✅ 4 个亮点已实施并有独立文档：
  - `docs/streamable-agent-resumable.md`（断点续传）
  - `docs/agent-trace.md`（可视化 trace）
  - `docs/feedback-dashboard.md` + `docs/feedback-to-fixture.md`（反馈闭环）
  - `docs/performance-benchmark.md`（压测）
- ✅ README "Performance" 章节 + 5 数字
- ⏳ 没有整合性的讲解文档（STAR 法则 + 预演答案 + 架构图）

## 交付物（5 件）

### 1. `docs/interview-guide.md`（主讲解文档）
**4 部分结构**：

#### Part 1 — 项目总览（5 分钟讲完）
- 一句话定位
- 技术栈一览表
- 4 个核心能力（AI Agent + RAG + 流式 + 评估）
- 4 周亮点的预告（"接下来重点讲 4 个亮点"）

#### Part 2 — 4 个亮点 STAR（30 分钟）
每个亮点独立 STAR（200 字/亮点，共 800 字）：
- **S**ituation：业务/用户痛点
- **T**ask：我的目标
- **A**ction：技术方案 + 3 个关键决策
- **R**esult：量化结果 + 数字

4 个亮点：
1. **断点续传流式 Agent** — 链接 `streamable-agent-resumable.md`
2. **可视化 Agent 调试** — 链接 `agent-trace.md`
3. **反馈→fixture 自动化闭环** — 链接 `feedback-to-fixture.md`
4. **生产压测报告** — 链接 `performance-benchmark.md`

#### Part 3 — 10 个高频问题预演答案（30 分钟）
基于已实施的技术选型，10 个最可能被问到的问题 + 1-2 段预演答案（150-200 字/题）：
1. 介绍一下你的项目？
2. RAG 链路里你做了什么优化？（Chroma 选型 / 知识库构建 / 检索增强）
3. Agent 怎么决定调哪个工具？（function calling + 4 个 tool + 重试）
4. 上下文怎么管理不会超 token？（token 阈值 + 分层摘要 + 增量压缩）
5. LLM 输出不稳定你怎么处理？（Zod 校验 + JSON 修复 + max_tokens）
6. 流式响应断线怎么办？（SSE Last-Event-ID + Redis streamStore + 字节级去重）
7. 怎么评估 Agent 质量？（10 fixture + 13 evaluator + mock/真实/CI/多采样）
8. 性能瓶颈在哪里？（Chroma 60% / DeepSeek 30% / JSON 5% / DB 5%）
9. 安全做过什么？（17 项 + bcrypt 12 + JWT 128 + SSRF 防护）
10. 接下来会怎么改进？（Redis POI 缓存 / 多 LLM provider / LangGraph）

#### Part 4 — Trade-off 论述（10 分钟）
3-5 个最重要的设计决策，每个 100-150 字：
- 为什么 SSE 而不是 WebSocket？
- 为什么 Chroma 而不是 Milvus？
- 为什么 Redis 缓存 + 内存缓存双层而不是单层？
- 为什么 in-memory token budget 而不是持久化？
- 为什么单 LLM provider 而不是多 provider 路由？

### 2. `docs/architecture-diagrams.md`（4 张 Mermaid 架构图）
4 张图，每张 ≤30 行 Mermaid：
- **系统架构图**：Vue 前端 → Express 后端 → Prisma/MySQL/Redis/Chroma/DeepSeek
- **Agent 时序图**：用户消息 → tripService → agentEngine → tool calls → LLM → SSE
- **上下文数据流**：message → token budget check → compress → summary
- **评估体系**：fixture → runner → evaluator → report

### 3. `README.md` 升级（已有 Performance，加 2 个新章节）
- **## Architecture**（3-5 句话 + 架构图链接）
- **## Highlights**（4 卡片，每卡片 1 句话 + 链接到详细文档）

### 4. `docs/demo-script.md`（演示脚本）
5-10 分钟演示的剧本：
- 0:00 - 0:30 项目介绍
- 0:30 - 2:00 演示 chat 流式（前端）
- 2:00 - 3:30 演示断点续传（kill 中间，刷新看续传）
- 3:30 - 5:00 演示 admin trace（admin dashboard）
- 5:00 - 6:30 演示反馈系统（点赞/转 fixture）
- 6:30 - 8:00 演示评估（pnpm eval 看报告）
- 8:00 - 9:00 压测数字（5 个 key number）
- 9:00 - 10:00 总结

**注**：**实际录视频不在本任务范围**（用 ffmpeg + 屏幕录制需要用户决定），但提供脚本让用户可自行录制。

### 5. `tasks/interview-checklist.md`（面试前 checklist）
20 项面试前 24 小时 checklist：
- [ ] README Performance 数字背熟
- [ ] 4 个亮点 STAR 能口述
- [ ] 10 个高频问题答案背熟
- [ ] 能画 4 张架构图
- [ ] demo 跑通（chat / 断点续传 / admin / eval）
- [ ] 数据库 seed 完整（eval-test 账号）
- [ ] 环境变量 .env.example 完整
- [ ] 1-2 个 follow-up 问题准备（如"Redis 集群怎么做"）
- [ ] ...

## 关键决策（需要用户确认）

1. **是否真录 demo 视频**？
   - 选项 A：只写 demo-script.md，用户自行决定录不录
   - 选项 B：用 asciinema / marp 录 markdown → 自动生成视频
   - **推荐 A**（录视频需用户决定时长/风格）

2. **架构图用什么格式？**
   - ✅ 决定：**4 张 Mermaid**（GitHub 自动渲染，diff 友好）
   - 备选：draw.io 不可行（未装，npm 也不支持）

3. **讲解文档用中文还是中英混合？**
   - ✅ 决定：**中英混合**（技术术语用英文 + 中文叙述）

## 不在本任务范围

- ❌ 录实际 demo 视频（仅写脚本）
- ❌ 写个人 blog（plan §10 加分项，本次不做）
- ❌ GitHub Profile README（用户自己决定）
- ❌ P3 跟进项（test-alert prod gate + fetch timeout，已 P3 留作后续）
- ❌ 重大代码改动（仅文档 + README 微调）

## 风险

| 风险 | 影响 | 应对 |
|---|---|---|
| STAR 答案太技术 | 面试官听不懂 | 写完后 AI 模拟 3 轮，迭代措辞 |
| 架构图 Mermaid 渲染失败 | GitHub 显示源码 | 用 mermaid.live 验证后再 commit |
| 10 个问题答案不准确 | 误导候选人 | 每个答案都引用具体 commit/file:line |
| 文档太长没人看 | 失价值 | Part 1 严格 5 分钟，每亮点 STAR ≤200 字 |

## 任务拆分（5 commit, 4 批）

### 批次 1（线性）
- **Task 1**: 写 `docs/interview-guide.md`（Part 1-4 全部） — **本任务最大头**

### 批次 2（并行）
- **Task 2**: 写 `docs/architecture-diagrams.md`（4 张 Mermaid）
- **Task 3**: 升级 `README.md`（加 ## Architecture + ## Highlights）

### 批次 3（线性）
- **Task 4**: 写 `docs/demo-script.md`（10 分钟脚本）

### 批次 4（并行）
- **Task 5**: 写 `tasks/interview-checklist.md`（20 项 checklist）
- **Task 6**: 最终验证（mermaid 渲染 / 链接正确 / 数字一致）

## 验证标准

- [ ] `docs/interview-guide.md` < 3000 行
- [ ] `docs/architecture-diagrams.md` 4 张图，GitHub 渲染成功
- [ ] README 新章节链接到所有新文档
- [ ] 5 个数字在文档里出现 ≥ 2 次（README + interview-guide）
- [ ] 10 个问题答案每个都引用具体 commit SHA 或 file:line
- [ ] `pnpm test` 仍 9 passed / 6 failed（基线保持）
- [ ] 所有内部链接用相对路径

## 预估时间

- Task 1（主文档）: 30-40 分钟
- Task 2（架构图）: 10 分钟
- Task 3（README 升级）: 10 分钟
- Task 4（demo 脚本）: 10 分钟
- Task 5（checklist）: 5 分钟
- Task 6（验证）: 5 分钟
- **总：~70-80 分钟**

比计划文档写的 5 天少，因为是**汇编已有内容**而非从零写。
