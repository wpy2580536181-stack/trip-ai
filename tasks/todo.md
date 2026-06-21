# 项目剩余待办（截至 2026-06-21）

> 详细规划见对应文档：
> - 安全：`tasks/security-fix-todo.md`（**17 项 P0-P3 全部完成**）
> - Agent 改进：`docs/agent-improvements.md`（17 项，测试体系 + 部分 P0 已交付）
> - 缓存：`docs/cache-optimization.md`（**P0+P1 已交付**，P2 跨用户共享待评估）
> - 上下文管理：`docs/context-management-improvements.md`（4 项已全部交付）
> - JSON 健壮性：`docs/llm-json-robustness.md`（**9 个失败模式已全部修复**）
> - 日志：`docs/pino-logging.md`（**已交付**，58 → 1 console 调用）

---

## 已完成（参考）

- ✅ Phase 1a/1b/2/3：AI agent + RAG + 对话记忆 + 行程历史 + 用户偏好 + 外部 API + POI 知识库
- ✅ 上下文管理 4 项：增量摘要 + 统一 token 阈值 + 分层摘要 + 重试
- ✅ LLM 缓存优化 P0+P1：固定 PREF_KEYS 顺序 + 摘要 append 模式
- ✅ JSON 健壮性 9 项：pick longest + 截断检测 + 嵌套 zod + 3 次重试
- ✅ Token Usage 模块：10 个 Task（`stats.routes.ts` + `TokenUsage.vue`）
- ✅ Phase 5 优先级队列：`services/llmGuard/semaphore.ts` 已实现
- ✅ 安全加固 17 项：JWT_SECRET 128 位 + bcrypt 12 + SSRF 防护 + 知识库 admin 鉴权 + 路由守卫 token 过期检查
- ✅ Pino 结构化日志：13 个 child logger + 脱敏 + reqId 贯穿

---

## 待完成（按价值排序）

### 🟡 中价值（按需）

#### 1. Agent 评估体系（`docs/agent-improvements.md:2.3`）
- [ ] 离线评估：5-10 个 fixture 行程需求，验证 RAG 召回质量
- [ ] 在线反馈：前端增加"回答有用/无用"按钮
- [ ] **价值**：上线前发现 80% 质量回归的关键手段

#### 2. 缓存 P2（`docs/cache-optimization.md` 第三阶段）
- [ ] 跨用户共享前缀（系统说明 + 工具描述）→ 待 P0+P1 真实数据验证后决定
- [ ] 缓存命中率监测 endpoint（`/api/admin/cache-stats`）
- [ ] **前置**：需要至少 1 周生产流量才能判断 P2 是否值得做

#### 3. 日志聚合（`docs/pino-logging.md` 未来优化）
- [ ] OpenTelemetry traceId 关联（看链路）
- [ ] Loki/ELK 远程推送（生产聚合）
- [ ] 日志采样（高流量时降本）

### 🟢 低价值（可延后）

#### 4. LangGraph 重构（`docs/agent-improvements.md:3.1`）
- [ ] 把 AgentExecutor 换成 LangGraph StateGraph
- [ ] **价值**：面试亮点 + 流式 + 中断恢复能力
- [ ] **风险**：LangGraph 学习曲线 + 重写工作量大

#### 5. CI/CD
- [ ] GitHub Actions：lint + type-check + 跑测试
- [ ] 自动部署（需 server 配合）

#### 6. 产品功能（`docs/agent-improvements.md` 一）
- [ ] 1.1 行程导出（PDF / Markdown）
- [ ] 1.2 多模态识别（图片景点）
- [ ] 1.3 行程协作
- [ ] 1.4 推送通知
- [ ] 1.5 PWA 离线

---

## 建议

按 ROI 排序，前三名都在"中价值"区（高价值全做完了）：

1. **Agent 评估体系**（最大价值）— 上线前必做，1-2 天工作量
2. **缓存命中率监测**（数据驱动决策）— 0.5 天，先看 P0+P1 实际效果再决定 P2
3. **CI/CD 基础**（防回归）— 0.5 天，lint + type-check 即可

如果短期内不再上生产，可以先按"评估 + 监测"组合做，知道真实效果再决定 LangGraph 重构是否值得。
