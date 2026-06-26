# 项目演示脚本（Demo Script）

> 5-10 分钟演示
> 配套 `docs/interview-guide.md`

## 使用说明

- **时长**：严格控制在 5-10 分钟
- **风格**：中英混合，screen 切镜 + 台词
- **节奏**：每个 section 标注时长
- **预备**：演示前 1 小时跑通所有命令，避免现场卡壳

## 演示流程

### 0:00 - 0:30 | 项目介绍（30s）

**Screen**: README.md 渲染页

**台词**:
> "trip-ai 是一个 AI 旅行规划助手。核心技术栈：Vue 3 + Express 5 + Prisma + LangChain，存储 MySQL/Redis/Chroma，LLM 用 DeepSeek。4 周前我加了 4 个亮点：断点续传流式 Agent、可视化 Agent 调试、反馈→fixture 自动化、生产压测报告。今天用 10 分钟演示 4 个亮点。"

**切镜**: 浏览器切到 chat 页面

---

### 0:30 - 2:00 | 演示 chat 流式（1m30s）

**Screen**: `http://localhost:5173/` chat 页面 + DevTools Network

**操作**:
1. 登录（账号: `eval-test` / 密码: `EvalTest@2026`）
2. 输入: "我想去北京玩 3 天，预算 5000 元"
3. 按 Enter，观察流式 chunk 输出
4. 打开 DevTools Network → 看 SSE 事件流

**台词**:
> "这是主 chat 页面。看流式输出——每个 chunk 是一个 SSE event。用户输入 '北京 3 天 5000 块'，agent 会自动调 4 个 tool：天气、距离、酒店、POI 检索，最后生成结构化行程。"

**切镜**: DevTools Network → Headers → 看 `text/event-stream` 和 `id:` 字段

---

### 2:00 - 3:30 | 演示断点续传（1m30s）

**Screen**: chat 页面 + DevTools Console

**操作**:
1. 重新发一个新消息: "上海有什么好吃的？"
2. 收到 1-2 个 chunk 后，**关掉网络**（DevTools → Network → Offline）
3. 等待 5 秒
4. **恢复网络**
5. 观察：客户端 EventSource 自动重连 + 续传

**台词**:
> "现在演示断点续传——这是 Week 1 的亮点。我关掉网络模拟断线。客户端用 EventSource 替代 fetch，SSE 原生 Last-Event-ID 头自动重连。看，恢复网络后从断点续推，**不重传已收 chunk**。服务端 Redis streamStore 持久化 sequence，重启不丢。"

**备选演示**: `docs/resumable-demo.html` 单文件 demo（不开服务也能演示）

**切镜**: admin dashboard

---

### 3:30 - 5:00 | 演示 admin trace（1m30s）

**Screen**: `http://localhost:5173/admin/feedback`

**操作**:
1. 在 admin dashboard 找一条 "高 token + 低满意度" 案例
2. 点击 "🔍 Trace" 按钮
3. 跳转 `/admin/trace?messageId=X`
4. 展示时间轴 + JSON 折叠

**台词**:
> "这是 Week 2 的亮点——可视化 Agent trace，类 LangSmith。点 '🔍 Trace' 跳到这次 chat 的全链路：5-10 个 step，含 4 个 tool 调用 + 1 个 complete。展开 JSON 看 tool 参数和返回。这是线上定位问题的高效工具——之前靠 grep 日志，现在秒级回放。"

**切镜**: 点 👍/👎 按钮

---

### 5:00 - 6:30 | 演示反馈系统（1m30s）

**Screen**: chat 页面 + admin dashboard

**操作**:
1. 在 chat 页面点 👍 一个回复
2. 切到 admin dashboard
3. 看反馈统计
4. 点 "📋 转 fixture" 按钮
5. 看 modal 流程 → 生成 YAML fixture
6. `cat trip-server/eval/fixtures/generated/xxx.yaml`

**台词**:
> "这是反馈系统——Week 1.5 实现的。用户在 chat 点 👍/👎，admin 在 dashboard 看统计，更关键的是 '📋 转 fixture' 按钮。一键把这次失败案例变成评估 fixture，下次 eval 自动覆盖。fixtureConverter 纯函数 + feedbackService 3 冲突分支处理。"

**切镜**: 终端

---

### 6:30 - 8:00 | 演示评估（1m30s）

**Screen**: 终端 + 浏览器

**操作**:
1. `cd trip-server && pnpm eval`
2. 看输出：10 fixture 跑完 + 报告
3. `open trip-server/eval/reports/report-*.html`
4. 展示 HTML 报告

**台词**:
> "评估体系——4 模式：mock LLM 跑 CI、真实 LLM 跑本地、3-5 次多采样取中位数、自动报告。10 fixture + 13 evaluator，evaluator 类型含 must_contain_keywords / must_not / regex / json_schema / semantic_match。fixture 用 YAML 描述，runner 扫双目录。"

**切镜**: README Performance 章节

---

### 8:00 - 9:00 | 压测数字（1m）

**Screen**: README + `docs/performance-benchmark.md`

**台词**:
> "最后是 Week 3 的压测报告。5 关键数字——
> 1. 单实例历史 QPS **6.67**（10 并发）
> 2. SSE 流式 P99 **47 秒**（10 并发，含真实 LLM）
> 3. LLM 缓存命中率 **40.2%**（49 相似请求，节省 ¥2/天）
> 4. /recommend P50 **29.1 秒**（10 不同请求）
> 5. 单流平均 chunk **1000+**（8-50 段 itinerary）
>
> 3 关键发现：(1) DeepSeek 上游是容量上限，conc=20 全失败；(2) Chroma 检索占 60% 延迟，加 Redis 缓存 ROI 最高；(3) 生产 rate limit 工作正常，登录 20/min/user 是预期。"

**切镜**: `docs/architecture-diagrams.md`

---

### 9:00 - 10:00 | 总结（1m）

**Screen**: 4 张 Mermaid 架构图

**台词**:
> "总结——trip-ai 完整覆盖 AI 应用开发 4 大方向：Agent 编排、RAG、流式、评估。技术上 LangChain + Chroma + Prisma + Pino 全栈推进。规模 8800 行 TS+Vue，56 测试。4 周亮点证明工程能力：能从 0 到 1 设计断点续传、做 LangSmith 级工具、跑真实压测拿数据。
>
> 接下来方向：(1) Redis POI 缓存减半 /recommend 耗时；(2) 多 LLM provider 路由解决上游限流；(3) LangGraph 多 Agent 重构。
>
> **问题环节**。"

---

## 应急预案

### 服务器挂了

1. 切换到 `docs/resumable-demo.html`（单文件 demo，不依赖服务）
2. 用截图 + README 替代
3. 重点讲"设计思路"而非"现场跑"

### 演示卡了

1. 跳过当前 section，下一个 section 优先
2. **优先级**：数字（0.5m）> 架构图（1m）> 亮点 demo（每个 1.5m）
3. 核心保 5 数字必须讲完

### 问题没准备

1. "这个问题我的设计是这样的——" 慢慢说，争取思考时间
2. 引用具体 commit SHA 或 file:line 增加可信度
3. 实在不会："这是个很好的点，我之后会深入研究"

### 网络慢/超时

1. 提前录屏备份（QuickTime 录 1 遍存桌面）
2. 现场跑失败时切录屏

---

## 录制检查清单

演示前 24 小时：
- [ ] Docker 起来（MySQL + Redis + Chroma）
- [ ] `pnpm dev` 跑通
- [ ] chat 跑通（含 SSE）
- [ ] 断点续传跑通（离线/恢复）
- [ ] admin trace 跑通（用 eval-test 账号）
- [ ] 反馈→fixture 跑通（点 "📋 转 fixture" 看 modal）
- [ ] `pnpm eval` 跑通（看 HTML 报告）
- [ ] 录屏备份（QuickTime 1 遍，5-10 分钟）

演示前 1 小时：
- [ ] 5 关键数字背熟
- [ ] 4 STAR 能口述
- [ ] 10 个问题答案背熟
- [ ] 4 张架构图能画
- [ ] 屏幕分辨率调好（适合现场投屏 1920×1080）
- [ ] 关闭无关通知（避免现场弹窗）

---

## 配套资源

- **讲解文档**：`docs/interview-guide.md`（4 部分 + 附录）
- **架构图**：`docs/architecture-diagrams.md`（4 张 Mermaid）
- **面试 checklist**：`tasks/interview-checklist.md`（20 项）
- **单文件 demo**：`docs/resumable-demo.html`（断点续传离线版）
