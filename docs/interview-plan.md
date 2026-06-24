# 面试亮点计划（2026-06-22 ~ 2026-07-22）

> **目标**：4 周内让项目在 AI 应用开发 / 后端全栈岗位面试中"有亮点可讲、有数据可引、有深度可挖"
> **岗位**：AI 应用开发工程师（RAG/Agent 方向） + 后端全栈
> **现状**：8800 行代码（5720 TS + 3055 Vue），核心架构完整，**但缺乏"亮点密度"**

---

## 1. 现状盘点

### 已完成的核心能力（面试基础分）
- AI Agent + RAG + 对话记忆 + 行程历史
- 4 个外部 API 工具（天气/距离/酒店/POI 检索）
- 上下文管理（token 阈值 + 分层摘要 + 增量压缩）
- 评估体系（10 fixture + 13 evaluator + mock/真实 + CI + 多采样 + 报告）
- 在线反馈系统（Prisma Feedback + 4 API + 前端 👍/👎）
- Pino 结构化日志 + 13 个 child logger
- 17 项安全加固（JWT 128 位 + bcrypt 12 + SSRF 防护）

### 真正缺什么（面试加分点）
- **生产可观测性**：agent 内部状态不可见，定位问题靠 grep 日志
- **流式可靠性**：断线/刷新导致整段重传
- **量化数据**：服务能扛多少 QPS？token 节省多少？缓存命中率？
- **设计 trade-off 论述**：决策过程没记录

---

## 2. 4 周计划总览

```
Week 1: 断点续传流式 Agent       (1 周)
Week 2: 可视化 Agent 调试工具    (1 周)
Week 3: 生产压测报告            (3-5 天)
Week 4: 项目讲解文档 + 收尾     (3-5 天)
```

| 亮点 | 面试能讲 | 价值 | 工作量 | 风险 |
|---|---|---|---|---|
| 1. 断点续传 | "我设计了带 SSE Last-Event-ID 的可恢复流" | 高 | 1 周 | 低 |
| 2. 可视化调试 | "我做了类似 LangSmith 的生产级工具" | 高 | 1 周 | 低 |
| 3. 压测数据 | "我的服务在 X 并发下 P99 是 Y ms" | 中高 | 3-5 天 | 低 |
| 4. 讲解文档 | STAR 法则 + 10 个高频问题预演 | 必备 | 3-5 天 | 零 |

---

## 3. 亮点 1：断点续传流式 Agent

**详细设计**：`docs/streamable-agent-resumable.md`

### 核心要解决
用户在流式收 AI 回复到一半时（任何原因）中断，能从断点继续，而不是整段重传。

### 实现方案（两层）

#### 方案 A：客户端 SSE Last-Event-ID（先做）
- 客户端改用 `EventSource`（原生支持自动重连 + Last-Event-ID 头）
- 服务端给每个 chunk 加 `id:` 字段（SSE 标准）
- 重连时浏览器自动带 `Last-Event-ID` 头
- 服务端从该 ID 开始重推

#### 方案 B：服务端持久化 + 续传（进阶）
- 服务端把每次 chunk 实时写 DB（带 sequence_id）
- 客户端断线重连时，先读 DB 历史 chunk → 再接续 SSE

### 关键边界
1. **agent 中断时工具还在跑**：服务端要能"等工具跑完再续"
2. **流式 chunk 顺序**：sequence_id 单调递增，乱序重排
3. **重复 chunk 处理**：客户端按 sequence_id 去重

### 面试能讲
> "我设计了一个带断点续传的 Streamable Agent。客户端用 SSE 原生的 Last-Event-ID 头自动重连，服务端给每个 chunk 加 sequence_id 标识顺序。比 LangChain 默认实现多考虑了 3 个边界：agent 中断时工具还在跑怎么办、客户端重复接收怎么办、sequence_id 间隙检测。"

### 实施计划
- Day 1-2: 服务端 chunk 加 `id:` 字段 + sequence_id 持久化
- Day 3-4: 客户端 `EventSource` 改造（替代 fetch 循环）
- Day 5-6: 边界处理 + 单元测试
- Day 7: 文档 + 演示视频

---

## 4. 亮点 2：可视化 Agent 调试工具

### 核心要解决
线上 agent 出问题时，开发者能**看到内部状态**——完整 prompt、每次 tool call、token 用量、响应时长。

### 三大视图

#### 时间线视图
```
[LLM]    ──────────────── 1200ms / 350 tokens ────────────────
   ↓ (思考)
[TOOL]   retrieve_knowledge("成都景点")  ─── 80ms ──→ 5 results
   ↓ (结果)
[TOOL]   getWeather("成都")  ─── 150ms ──→ 28°C
   ↓ (结果)
[LLM]    ──────────────── 800ms / 250 tokens ────────────────
   ↓ (输出)
[STREAM] chunk-by-chunk 流式输出 (5s)
```

#### Prompt 视图
```
=== SYSTEM ===
你是一个专业的旅行规划师助手...
[展开/折叠 1500 字符]

=== HISTORY (3 messages) ===
[user] 带父母去成都
[assistant] 好的，我来规划...
[展开/折叠]

=== USER ===
带父母去成都玩 3 天
```

#### 统计视图
- 总 token：2.3k（prompt 1.8k + completion 0.5k）
- 总耗时：8.2s
- 工具调用：retrieve_knowledge × 2 / getWeather × 1
- 缓存命中：1/3

### 面试能讲
> "我做了一个**生产级 Agent 可观测性工具**——pino 结构化日志 + 后端 trace 聚合 + admin 页面三大视图。线上出了 3 次质量问题，我用这个工具在 5 分钟内定位到是 retrieve_knowledge 的 query rewrite 权重问题。之前排查同类问题要 grep 30 分钟日志。"

### 实施计划
- Day 1-2: 后端 trace 聚合接口（按 conversationId + time range）
- Day 3-4: 前端 admin 页面框架 + 时间线视图
- Day 5: Prompt 视图 + 统计视图
- Day 6-7: 测试 + 文档

---

## 5. 亮点 3：生产压测报告

### 核心要解决
- 服务能扛多少 QPS？P99 多大？
- 流式接口在 100 并发下表现？
- LLM 缓存命中率？省了多少 token？

### 压测矩阵

| 场景 | 工具 | 指标 |
|---|---|---|
| 普通 HTTP（登录/查历史） | autocannon | QPS / P99 / 错误率 |
| SSE 流式 chat | k6 + 脚本 | 并发流数 / 流延迟 / CPU |
| LLM 路由 | 真实调用 | token/s / 成本 / 命中率 |
| 缓存效果 | 50 个相似问题 | 命中分布 / 节省比例 |

### 输出物
- `docs/performance-benchmark.md`（详细报告）
- `docs/performance-charts/`（图表：QPS-P99 曲线 / 缓存命中分布）
- README "Performance" 章节（5 个关键数字）

### 面试能讲
> "我的服务在 100 并发 SSE 流式下 P99 是 2.3s，单实例 QPS 达 450。瓶颈在 Chroma 向量检索（贡献 60% 延迟），通过加 Redis 缓存后降到 1.1s。LLM 缓存命中率 35%，每天节省约 50 元。"

### 实施计划
- Day 1: 装 autocannon/k6，写测试脚本
- Day 2-3: 跑压测 + 收集数据
- Day 4-5: 写报告 + 优化建议

---

## 6. 亮点 4：项目讲解文档

### 内容大纲

#### 第 1 部分：项目总览（5 分钟讲完）
- 一句话定位
- 5 大能力（agent / RAG / 记忆 / 评估 / 反馈）
- 数字（8800 行 / 56 单元测试 / 50-70% eval pass rate / 30%/hr feedback 限流）

#### 第 2 部分：技术亮点（按 STAR 法则组织）
每个亮点独立 STAR：
- **Situation**：用户/业务痛点
- **Task**：我的目标
- **Action**：技术方案 + 关键决策
- **Result**：量化结果

预计 5-6 个亮点 × STAR，每个 200 字 = 1000-1200 字

#### 第 3 部分：10 个高频问题预演答案
1. 介绍一下你的项目？
2. RAG 链路里你做了什么优化？
3. Agent 怎么决定调哪个工具？
4. 上下文怎么管理不会超 token？
5. LLM 输出不稳定你怎么处理？
6. 怎么评估 agent 质量？
7. 流式输出怎么做？
8. 缓存策略怎么设计？
9. 安全性做了什么？
10. 如果让你重做一遍会改什么？

#### 第 4 部分：trade-off 论述
- 为什么选 Chroma 而不是 Pinecone？
- 为什么用 pino 而不是 winston？
- 为什么 system prompt 不嵌 JSON？
- 为什么不用 LangGraph？

### 实施计划
- Day 1-2: 写第 1-2 部分（项目总览 + STAR）
- Day 3: 写第 3 部分（10 个高频问题）
- Day 4: 写第 4 部分（trade-off）
- Day 5: 录 demo 视频（5-10 分钟）

---

## 7. 整体时间线

```
6/22 - 6/28  Week 1  [断点续传]
6/29 - 7/05  Week 2  [可视化调试]
7/06 - 7/12  Week 3  [压测报告]
7/13 - 7/22  Week 4  [讲解文档 + 收尾]
```

每周末做一次 self-review：
- 跑 `npm test` + `npm run eval`（确保没回归）
- 检查 commit message 是否清晰
- 在 tasks/lessons.md 记录遇到的问题和解决方案

---

## 8. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| LangGraph 学习曲线 | 阻碍多 Agent 实现 | 改用 LangChain 原生 sub-agent 简化版 |
| 多模态 API 成本 | 压测成本 | 用 mock 数据先验证流程，真接口只在 demo 时用 |
| 压测环境不稳 | 数据不准 | 用同一台机器、同一时段、跑 3 次取中位数 |
| 文档写不好 | 表达不清 | 找朋友/AI 模拟面试跑 3 次，每次迭代 |
| 时间不够 | 4 个亮点只完成 2 个 | **优先 1 + 2**，压测和文档可后置 |

---

## 9. 成功标准

### 第 1 周结束
- ✅ SSE Last-Event-ID 头生效
- ✅ 客户端 EventSource 自动重连
- ✅ 单元测试覆盖断点续传 3 个边界

### 第 2 周结束
- ✅ admin 页面 3 大视图可访问
- ✅ 一次完整 chat 后能在 admin 看到全链路

### 第 3 周结束
- ✅ 5 数字 + 1 报告 + 1 README 章节

### 第 4 周结束
- ✅ 项目讲解文档 5 个 STAR + 10 个预演答案
- ✅ demo 视频 5-10 分钟
- ✅ 整体 1.5-2 小时能讲完整个项目

---

## 10. 加分项（可选）

- **架构图**：用 Mermaid 或 draw.io 画 4 张图（系统架构 / Agent 时序 / 上下文数据流 / 评估体系）
- **README 升级**：加 Project Highlights / Performance / Architecture 三个章节
- **demo 视频**：录一段 5-10 分钟的"项目介绍 + 代码演示"
- **个人 blog**：把"为什么这样设计"写成 3-5 篇技术博客
- **GitHub Profile**：把项目放在 pin 位置，加 README 截图

---

## 11. 立即行动

**下一步**：先写**断点续传设计文档**（你已要求）。写完你看：
- 方案 A vs B 选哪个？
- 服务端 sequence_id 用内存还是 DB？
- 客户端 EventSource 还是自己实现 fetch 重连？

确认设计后再动手写代码。
