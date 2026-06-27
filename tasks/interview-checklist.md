# 面试前 Checklist

> 面试前 24 小时检查
> 配套 `docs/interview-guide.md` + `docs/demo-script.md`

## 文档准备（5 项）

- [ ] **README.md** 通读 1 遍，确认 3 章节（Performance / Architecture / Highlights）齐全
- [ ] **4 个亮点详细文档** 各读 1 遍：
  - [ ] `docs/streamable-agent-resumable.md`
  - [ ] `docs/agent-trace.md`
  - [ ] `docs/feedback-to-fixture.md`
  - [ ] `docs/performance-benchmark.md`
- [ ] **interview-guide.md** 通读 1 遍，10 个高频问题答案背熟
- [ ] **architecture-diagrams.md** 4 张图能口头画出
- [ ] **demo-script.md** 5-10 分钟流程过 1 遍

## 环境准备（8 项）

- [ ] **Docker 起来**：`docker compose up -d`（MySQL + Redis + Chroma）
- [ ] **数据库 seed 完整**：`pnpm prisma db seed`（含 eval-test 账号）
- [ ] **.env 完整**：参考 `.env.example`，所有 API key 填好
- [ ] **pnpm dev 跑通**：`http://localhost:5173` + `:8080` 都正常
- [ ] **chat 跑通**：发 1 条消息，看 SSE 流式输出
- [ ] **断点续传跑通**：离线/恢复测试 1 次
- [ ] **admin trace 跑通**：用 eval-test 账号点 "🔍 Trace"
- [ ] **eval 跑通**：`pnpm eval` 跑完 10 fixture，看 HTML 报告

## 演示准备（4 项）

- [ ] **录屏备份**：QuickTime 录 1 遍 5-10 分钟 demo，存桌面
- [ ] **单文件 demo 备用**：`docs/resumable-demo.html` 能打开（断网时备选）
- [ ] **截图准备**：README 渲染页 + 4 张架构图 + 5 数字表格（3 张图）
- [ ] **屏幕分辨率**：1920×1080（适合投屏），关闭无关通知

## 知识准备（10 项）

- [ ] **5 关键数字背熟**：QPS 6.67 / SSE P99 47s / Cache 40.2% / LLM P50 29.1s / 1000+ chunks
- [ ] **4 STAR 能口述**：每个 200 字，不看文档流利讲完
- [ ] **10 个高频问题答案背熟**：`docs/interview-guide.md` Part 3
- [ ] **5 trade-off 能讲**：每个 100-150 字
- [ ] **架构图能画**：4 张 Mermaid 图在白板上复现
- [ ] **关键 commit SHA 背 5 个**：`b853530` / `d9e82f9` / `7d5d72d` / `0841296` / `a688cbd`
- [ ] **关键 file:line 背 5 个**：`tripService.ts:82` / `agentEngine.ts:17` / `contextManager.ts:45` / `feedbackService.ts` / `config/llm.ts:8-15`
- [ ] **3 关键发现能讲**：DeepSeek 上游限流 / Chroma 60% 延迟 / Cache 40% 命中率
- [ ] **3 改进方向能讲**：Redis POI 缓存 / 多 LLM provider / LangGraph 重构
- [ ] **17 项安全能列 5 项**：bcrypt 12 / JWT 128 / SSRF 防护 / Pino 结构化日志 / rate limit

## 应急预案（3 项）

- [ ] **服务器挂了**：切换 `docs/resumable-demo.html` 单文件 demo
- [ ] **演示卡了**：跳过当前 section，**核心保 5 数字**讲完
- [ ] **问题没准备**："这是个很好的点，我之后会深入研究" + 引用 commit SHA 增加可信度

## 面试后（2 项）

- [ ] **记录问题**：面试官问了什么、答得怎么样
- [ ] **更新文档**：高频新问题加到 `interview-guide.md` Part 3
