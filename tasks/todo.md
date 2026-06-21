# 项目剩余待办（截至 2026-06-20）

> 详细规划见对应文档：
> - 安全：`tasks/security-fix-todo.md`（P0 已推送，P1+P2 未动）
> - Agent 改进：`docs/agent-improvements.md`（17 项，P0 测试体系已部分交付）
> - 缓存：`docs/cache-optimization.md`（P0+P1 已推送，P2 跨用户共享待评估）
> - 上下文管理：`docs/context-management-improvements.md`（4 项已全部交付）
> - JSON 健壮性：`docs/llm-json-robustness.md`（已全部交付）

---

## 已完成（参考）

- ✅ Phase 1a/1b：AI agent + RAG + 对话记忆 + 行程历史 + 用户偏好
- ✅ Phase 2：4 个外部 API 工具 + 行程优化 + 工具状态展示
- ✅ Phase 3：POI 导入 + 知识 CRUD + 管理 UI
- ✅ 上下文管理：增量摘要 + 统一 token 阈值 + 分层摘要 + 重试
- ✅ LLM 缓存优化 P0+P1：固定 PREF_KEYS + 摘要 append 模式
- ✅ JSON 健壮性：9 个失败模式 + 强校验 + 重试
- ✅ Token Usage 模块：10 个 Task（`stats.routes.ts` + `TokenUsage.vue`）
- ✅ Phase 5 优先级队列：已在 `services/llmGuard/semaphore.ts` 实现

---

## 待完成（按价值排序）

### 🔴 高价值（推荐立刻做）

#### 1. 安全加固 P1（密码重置 + 限流）
- [ ] P1-1：密码重置令牌暴露给前端（userService.ts:162-179）→ 接入邮件或移除 token 返回
- [ ] P1-2：用户枚举漏洞（注册/重置接口）→ 统一错误消息
- [ ] P1-3：景点 CRUD 缺少权限校验（knowledge.routes.ts）→ admin 鉴权
- [ ] P1-4：登录接口无速率限制（已部分）→ 确认 `authLimiter` 覆盖
- [ ] P1-5：知识库接口无速率限制

#### 2. 可观测性 P0（pino 结构化日志）
- [ ] 替换 `console.log/warn/error` 为 pino logger
- [ ] 请求 ID 中间件（req.id 贯穿日志）
- [ ] 关键路径日志：LLM 调用、工具调用、压缩触发、缓存命中

#### 3. 安全加固 P2
- [ ] P2-6：SSRF 风险（getWeather 工具）→ 限制 wttr.in 等外部 URL 白名单
- [ ] P2-7：知识管理接口无速率限制
- [ ] P2-8：LIKE 查询性能（knowledgeService 搜索路径）

### 🟡 中价值（按需）

#### 4. Agent 评估体系（`docs/agent-improvements.md:2.3`）
- [ ] 离线评估：5-10 个 fixture 行程需求，验证 RAG 召回质量
- [ ] 在线反馈：前端增加"回答有用/无用"按钮

#### 5. 缓存 P2（`docs/cache-optimization.md` 第三阶段）
- [ ] 跨用户共享前缀（系统说明 + 工具描述）→ 待 P0+P1 真实数据验证后决定
- [ ] 缓存命中率监测 endpoint（`/api/admin/cache-stats`）

### 🟢 低价值（可延后）

#### 6. LangGraph 重构（`docs/agent-improvements.md:3.1`）
- [ ] 把 AgentExecutor 换成 LangGraph StateGraph
- [ ] 价值：面试亮点 + 流式 + 中断恢复能力

#### 7. CI/CD
- [ ] GitHub Actions：lint + type-check + 跑测试
- [ ] 自动部署（需 server 配合）

#### 8. 产品功能（`docs/agent-improvements.md` 一）
- [ ] 1.1 行程导出（PDF / Markdown）
- [ ] 1.2 多模态识别（图片景点）
- [ ] 1.3 行程协作
- [ ] 1.4 推送通知
- [ ] 1.5 PWA 离线

---

## 立即建议（按 ROI）

1. **P1-1 密码重置**（20 行改动，关掉"任何人能改任意密码"的洞）
2. **P1-2 用户枚举**（5 行改动）
3. **P1-3 知识库 admin 鉴权**（5 行中间件）
4. **pino 结构化日志**（1 小时工作量，500 行 console 替换）
5. **P2-6 SSRF 防护**（10 行 URL 校验）

预计 1 个工作日内全部完成。
