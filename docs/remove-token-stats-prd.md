# 删除「Token 用量统计」功能 PRD

> **文档状态**：草案 v1.0
> **作者**：AI 助手（基于代码调研）
> **日期**：2026-08-01
> **下游消费者**：开发团队
> **上游输入**：主理人需求「删除 tokens 用量统计功能」+ 代码调研报告

---

## 1. 项目信息

| 字段 | 内容 |
|---|---|
| **项目名称** | trip（AI 旅行规划系统，trip-backend + trip-front） |
| **项目类型** | 功能删除（清理） |
| **原始需求复述** | 删除「Token 用量统计」功能。该功能当前包含：数据落库（token_usage_logs 表）、后端统计接口（/api/stats/token-usage/*）、前端入口（Home 卡片 + 侧边栏菜单）与展示页面（TokenUsage.vue）。 |

### 1.1 功能现状速览

```
LLM 调用完成（LangChain callback, config/llm.py 注入）
  └─→ token_tracker.py TokenTrackingCallback.on_llm_end 提取 usage
        ├─→ token_monitor.record() → 落库 token_usage_logs 表（异步旁路，失败不阻断）
        └─→ token_budget_manager.record_*_usage()（内存计数器，供预算守卫）
agent 编排完成（agent_engine.py 3 处直接 token_monitor.record）
读取侧：stats_controller.py（3 个 API）→ stats_service.py → TokenUsageLog 表
前端：Home.vue 入口卡片 / Sidebar 菜单 → router /token-usage → TokenUsage.vue
```

---

## 2. 删除范围与边界（做什么 / 不做什么）

### 2.1 ✅ 做：删除「统计」链路

| 层面 | 内容 |
|---|---|
| **数据库** | 删除 `token_usage_logs` 表对应的 ORM 模型 `TokenUsageLog`；存量表数据保留在库中（见 4.4），不主动 DROP |
| **后端接口** | 删除 `GET /api/stats/token-usage/summary`、`/stats`、`/logs` 三个 API 及路由注册（stats_controller.py、main.py 挂载） |
| **后端服务** | 删除 stats_service.py、token_monitor.py（落库监控）；token_tracker.py 中仅保留 budget 计数部分 |
| **agent 落库点** | 删除 agent_engine.py 中 3 处 `token_monitor.record(...)` 调用（保留 complete 事件的 usage 回传，供 message.metadata 使用） |
| **模型关系** | 删除 user.py / conversation.py 中 `token_logs` relationship；清理所有 `import src.models.token_usage_log` noqa 引用（5 个 scripts + 2 个 tasks） |
| **前端** | 删除 Home.vue「Token 用量」卡片、Sidebar「Token 用量」菜单、router /token-usage 路由、TokenUsage.vue 页面、api/tokenUsage.ts |
| **测试** | 删除 tests/test_stats_controller.py、tests/test_models.py 中 TestTokenUsageLogModel、conftest.py 中相关 import |
| **文档** | 更新 README.md API 表；docs/ 中描述性引用后置处理 |

### 2.2 ❌ 不做：保留（明确排除）

| 保留项 | 原因 |
|---|---|
| **预算守卫**（token_budget.py + middleware/token_budget_guard.py + token_tracker.py 的 budget 部分） | 对话/推荐请求的 429/503 流量保护，内存计数，**不依赖** token_usage_logs 表；删除会导致超预算请求失控 |
| **高 token + 低满意度案例**（feedback_service.get_high_token_low_satisfaction + AdminFeedbackDashboard.vue 独立入口） | 数据源是 `messages.metadata.usage`，非统计表；仅在 TokenUsage.vue 内的区块随页面删除 |
| **agent-trace / trace 接口**（admin_service.py、AdminTrace.vue） | 数据源为 message.metadata，非统计表 |
| **usage 展示**（Chat.vue 等 SSE complete 事件的 usage 字段、eval/ 目录、AdminFeedbackDashboard 聚合） | 属于消息元数据链路，与统计表无关 |
| **utils/tokens.py、summary_service.py** | 对话压缩/窗口 token 估算，与用量统计无关 |
| **JWT 认证、rate_limiter、concurrency_guard** | 完全不同功能 |
| **settings.token_budget_user/global 字段** | 仅被 stats_service 读取，删除后成为死配置；是否一并清理列入后续可选（本 PRD 默认保留，零风险） |

---

## 3. 详细删除清单

### 3.1 删除文件（5 后端 + 4 前端 + 2 测试）

| 文件 | 说明 |
|---|---|
| `trip-backend/src/models/token_usage_log.py` | ORM 模型 |
| `trip-backend/src/services/stats_service.py` | 统计 service |
| `trip-backend/src/controllers/stats_controller.py` | 3 个 API |
| `trip-backend/src/services/agent/token_monitor.py` | 落库监控（无预算职责，可整删） |
| `trip-backend/tests/test_stats_controller.py` | stats API 测试 |
| `trip-front/src/api/tokenUsage.ts` | 前端 API |
| `trip-front/src/views/TokenUsage.vue` | 展示页面（含 admin 高 token 区块，随页面删除） |
| `trip-backend/src/services/agent/__init__.py` 导出 | 移除 token_monitor 导出（L25/L59） |

### 3.2 修改文件（删除引用）

| 文件 | 改动点 |
|---|---|
| `src/services/agent/token_tracker.py` | 删 token_monitor 落库调用（L64-81）；**保留** token_budget_manager 更新（L83-98） |
| `src/services/agent/agent_engine.py` | 删 L24-25 import 及 L366/L501/L623 三处 token_monitor.record |
| `src/config/llm.py` | 确认 callback 链中仅保留 token_tracker 的 budget 职责，无需改动则不动 |
| `src/main.py` | 删 L197-198 stats_router 注册 |
| `src/models/user.py` | 删 L77 `token_logs` relationship |
| `src/models/conversation.py` | 删 L59-63 `token_logs` relationship |
| `create_tables.py` | 删 L18 TokenUsageLog import |
| `scripts/migrate_mysql_to_pg.py` | 迁移表清单删 `token_usage_logs`；删 noqa import |
| `scripts/ingest_spot_docs.py`、`fetch_wiki.py`、`pgvector_reindex.py`、`e2e_m1_chroma_sync.py` | 删 `import src.models.token_usage_log # noqa` |
| `src/services/tasks/post_chat.py`、`wiki_fetch.py` | 删 noqa import（避免删除模型后 ImportError / mapper 链断裂 InvalidRequestError） |
| `tests/conftest.py`、`tests/test_models.py` | 删相关 import 与 `TestTokenUsageLogModel` |
| `trip-front/src/router/index.ts` | 删 /token-usage 路由（L66-70） |
| `trip-front/src/views/Home.vue` | 删 Token 用量卡片（L168-171） |
| `trip-front/src/components/layout/Sidebar.vue` | 删菜单项（L33） |
| `README.md` | 删 L101 API 条目 |

### 3.3 保留（勿动）

- `src/middleware/token_budget_guard.py`、`src/services/agent/token_budget.py`、`tests/test_middleware.py::TestTokenBudgetGuard`、`tests/test_chat_controller.py` 的 dependency override
- feedback / admin trace / Chat.vue usage 展示 / eval/ 目录

---

## 4. 验收标准（Definition of Done）

### 4.1 功能层面

- [ ] 前端登录后首页无「Token 用量」卡片，侧边栏无「Token 用量」菜单项，/token-usage 直接访问 → 404 或重定向（不白屏不报错）
- [ ] 后端 `GET /api/stats/token-usage/*` 三个接口返回 404
- [ ] 对话（chat）、推荐（recommend）、推荐变体（recommend-variants）主流程不受影响，SSE 正常流式输出
- [ ] 对话/推荐请求的预算守卫行为不变（超限仍返回 429/503）
- [ ] complete 事件仍回传 usage，Chat.vue 展示、message.metadata.usage 写入、高 token 低满意度案例（AdminFeedbackDashboard）、admin agent-trace 均不受影响

### 4.2 代码层面

- [ ] 全仓 grep 无 `token_usage_logs`、`TokenUsageLog`、`token_monitor`、`stats_service`、`token-usage` 残留引用（docs/ 描述性文档除外）
- [ ] 后端启动正常（create_tables.py 执行无 mapper 报错）
- [ ] arq worker（post_chat / wiki_fetch 任务）启动正常，无 InvalidRequestError
- [ ] 5 个 scripts 可正常 import（无 ImportError）

### 4.3 测试层面

- [ ] `pytest` 全量通过（原 stats/模型相关测试删除后，其余测试无 import 报错）
- [ ] 前端 `pnpm build` 通过（无 tokenUsage.ts / TokenUsage.vue 悬空引用）
- [ ] 前端 `pnpm lint` 通过（如有 lint 脚本）

### 4.4 数据层面

- [ ] 存量 `token_usage_logs` 表保留在库中（不 DROP，便于回滚）；如需清理另行手动执行

---

## 5. 风险清单

| # | 风险 | 等级 | 缓解措施 |
|---|---|---|---|
| R1 | **token_tracker.py 误删 budget 计数** → 预算守卫失效，超预算请求不再被拦截 | 高 | 改动时单独校验：token_budget_manager 更新代码行保留；用 test_middleware.py::TestTokenBudgetGuard + test_chat_controller.py 回归验证 |
| R2 | **SQLAlchemy mapper 关系链断裂** → 删除 User/Conversation 的 token_logs relationship 后，tasks/scripts 进程启动报 InvalidRequestError | 中 | 删除模型后立即验证 arq worker 与 5 个 scripts 可启动；所有 noqa import 同步清理 |
| R3 | **前端悬空引用** → 漏删某处 import 导致 build 失败 | 中 | 全仓 grep 兜底 + pnpm build 验证 |
| R4 | **遗漏后端 import 残留** → 启动时 ImportError | 中 | grep 兜底 + 后端启动冒烟 |
| R5 | **误删 agent-trace / feedback 高 token 功能**（名字带 token） | 中 | 清单明确排除项（3.3），代码评审时对照 |
| R6 | **TokenUsage.vue 中 admin 高 token 区块删除后**，该数据仍可从 AdminFeedbackDashboard 查看，无功能损失 | 低 | 已确认存在独立入口，文档记录 |
| R7 | **settings.token_budget_user/global 成为死配置** | 低 | 本 PRD 默认保留；后续如需清理单独立项 |
| R8 | **存量数据无法回滚**（若误删表） | 低 | 表不 DROP；代码删除均有 git 可回滚 |

---

## 6. 实施建议（供开发参考）

1. **顺序**：后端模型/服务 → 引用清理 → 前端 → 测试 → 文档
2. **关键点**：token_tracker.py 修改是最敏感的一步（R1），建议单独 commit 并跑预算守卫相关测试
3. **验证**：按第 4 节验收标准逐项执行；对话主流程用现有 eval 或手动冒烟覆盖

---

## 7. 附录：关键代码位置索引

| 位置 | 说明 |
|---|---|
| `trip-backend/src/services/agent/token_tracker.py:64-81` | 落库调用（删除），`:83-98` budget 计数（保留） |
| `trip-backend/src/services/agent/agent_engine.py:366/501/623` | token_monitor.record 落库点 |
| `trip-backend/src/services/agent/token_monitor.py:77-109` | `_save_to_db` 独立 session 落库 |
| `trip-backend/src/models/token_usage_log.py` | 模型，表 token_usage_logs |
| `trip-backend/src/controllers/stats_controller.py` | 3 个 API 路由 |
| `trip-front/src/views/TokenUsage.vue` | 展示页（558 行） |
| `trip-front/src/router/index.ts:66-70` | 路由 |
| `trip-front/src/views/Home.vue:168-171`、`components/layout/Sidebar.vue:33` | 入口 |
