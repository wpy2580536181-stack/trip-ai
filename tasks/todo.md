# 项目剩余待办（截至 2026-06-22）

> 详细规划见对应文档：
> - 评估体系：`docs/agent-eval.md` + `docs/online-feedback.md`（**MVP + 真实 + CI + 多采样 + 报告 已交付**）
> - 安全：`tasks/security-fix-todo.md`（**17 项 P0-P3 全部完成**）
> - Agent 改进：`docs/agent-improvements.md`（17 项，**评估体系 = 17 项中的核心 6 项**）
> - 缓存：`docs/cache-optimization.md`（**P0+P1 已交付**，P2 跨用户共享待评估）
> - 上下文管理：`docs/context-management-improvements.md`（4 项已全部交付）
> - JSON 健壮性：`docs/llm-json-robustness.md`（**9 个失败模式已全部修复**）
> - 日志：`docs/pino-logging.md`（**已交付**，58 → 1 console 调用）
> - 反馈系统：`docs/online-feedback.md`（**已交付**，11 单元测试 + e2e 通过）

---

## 已完成（参考）

### 核心功能
- ✅ Phase 1a/1b/2/3：AI agent + RAG + 对话记忆 + 行程历史 + 用户偏好 + 外部 API + POI 知识库
- ✅ Token Usage 模块：10 个 Task（`stats.routes.ts` + `TokenUsage.vue`）
- ✅ Phase 5 优先级队列：`services/llmGuard/semaphore.ts`
- ✅ 在线反馈系统：Prisma Feedback 表 + 4 API + 前端 👍/👎 + admin 统计

### 质量改进
- ✅ 上下文管理 4 项：增量摘要 + 统一 token 阈值 + 分层摘要 + 重试
- ✅ LLM 缓存优化 P0+P1：固定 PREF_KEYS 顺序 + 摘要 append 模式
- ✅ JSON 健壮性 9 项：pick longest + 截断检测 + 嵌套 zod + 3 次重试
- ✅ 安全加固 17 项：JWT_SECRET 128 位 + bcrypt 12 + SSRF 防护 + 知识库 admin 鉴权 + 路由守卫
- ✅ Pino 结构化日志：13 个 child logger + 脱敏 + reqId 贯穿

### 评估体系（2026-06-21/22 重点）
- ✅ 10 fixture + 13 evaluator + 56 单元测试
- ✅ mock agent + 真实 agent（HTTP 调 /api/trip/chat + SSE 解析 + 重试）
- ✅ CI 集成：`.github/workflows/eval.yml`（PR 跑 mock + typecheck，nightly 跑真实）
- ✅ 多采样多数投票（`--samples N`）
- ✅ 报告存档（`eval-reports/YYYY-MM-DD_HH-MM-SS_*.json`）
- ✅ 4 个真实 bug 修复：getWeather 强制、避免语境、宠物避雷、工具名大小写
- ✅ 真实 pass rate：单采样 50-70%，三采样多数 60-70%

---

## 待完成（按价值排序）

### 🟡 中价值（按需）

#### 1. 反馈系统扩展（`docs/online-feedback.md` 后续）
- ⏳ **admin dashboard 页面**：可视化 stats + recentDownComments（前端 + 路由）
- ⏳ **自动告警**：连续 1 小时 satisfactionRate < 0.5 触发飞书/Slack
- ⏳ **反馈 → fixture**：把负反馈自动转成 eval fixture（防止同类问题回归）
- **价值**：把"在线反馈"从纯统计变成质量改进闭环

#### 2. 缓存 P2（`docs/cache-optimization.md` 第三阶段）
- ⏳ 跨用户共享前缀（系统说明 + 工具描述）→ 待 P0+P1 真实数据验证后决定
- ⏳ 缓存命中率监测 endpoint（`/api/admin/cache-stats`）
- **前置**：需要至少 1 周生产流量才能判断 P2 是否值得做

#### 3. 日志聚合（`docs/pino-logging.md` 未来优化）
- ⏳ OpenTelemetry traceId 关联（看链路）
- ⏳ Loki/ELK 远程推送（生产聚合）
- ⏳ 日志采样（高流量时降本）

### 🟢 低价值（可延后）

#### 4. 真实 LLM token 用量统计
- ⏳ 后端 SSE 加 usage 字段（prompt/completion/total）
- ⏳ eval 输出 AgentOutput.tokens 真实数据
- ⏳ 前端 TokenUsage.vue 关联 feedback 显示"高 token + 低满意度"案例
- **价值**：识别哪些 case 烧 token 多但质量低（优化 ROI）

#### 5. LangGraph 重构（`docs/agent-improvements.md:3.1`）
- ⏳ 把 AgentExecutor 换成 LangGraph StateGraph
- **价值**：面试亮点 + 流式 + 中断恢复能力
- **风险**：LangGraph 学习曲线 + 重写工作量大

#### 6. 完整 CI/CD
- ✅ GitHub Actions eval（已交付）
- ⏳ GitHub Actions lint + typecheck 前端
- ⏳ 自动部署（需 server 配合）

#### 7. 产品功能（`docs/agent-improvements.md` 一）
- ⏳ 1.1 行程导出（PDF / Markdown）
- ⏳ 1.2 多模态识别（图片景点）
- ⏳ 1.3 行程协作
- ⏳ 1.4 推送通知
- ⏳ 1.5 PWA 离线

---

## 建议（按 ROI）

前 3 名都在中价值区：

1. **反馈 → fixture 自动化**（最大价值）— 把真实负反馈转成 fixture，让评估系统自我进化
2. **admin dashboard**（快速见效果）— 1 天工作量，让非技术人员也能看反馈
3. **真实 token 统计**（优化 ROI）— 找出"高 token + 低满意度"案例，针对性优化

如果短期内不再上生产，可以按 "反馈 → fixture" + "admin dashboard" 组合做，让反馈系统真正产生改进价值。
