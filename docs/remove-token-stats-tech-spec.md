# 删除「Token 用量统计」功能 — 技术方案（Tech Spec）

> **文档版本**：v1.0
> **创建日期**：2026-08-01
> **目标读者**：后端研发 / 前端研发 / 评审人
> **关联文档**：[删除 Token 用量统计 PRD](./remove-token-stats-prd.md)
> **评审状态**：⏳ 待评审

---

## 0. TL;DR

删除 Token 用量统计的**读、写、展**三条链路（表 / 接口 / 页面），保留**预算守卫**（429/503 流量保护）与**消息元数据 usage**（SSE complete 事件、trace、高 token 低满意度案例）。共删除 10 个文件、修改 20 个文件、新增 0 个文件。核心敏感点仅一处：`token_tracker.py` 必须保留 budget 计数分支（风险 R1）。

---

## 1. 架构事实（代码级）

### 1.1 两条独立链路（必须分清）

| | 统计链路（本次删除） | 预算链路（本次保留） |
|---|---|---|
| 数据源 | `token_usage_logs` 表（SQLAlchemy ORM） | `TokenBudgetManager` 内存计数器（进程内单例） |
| 写入 | `token_monitor.record()`（DB）+ 内存环形缓冲 | `token_budget_manager.record_user_usage/record_global_usage` |
| 读取 | `stats_controller.py` 3 个 API | `token_budget_guard.py` 中间件（429/503） |
| 失败影响 | fire-and-forget，异常仅 log，**不阻断主流程** | 超限**直接拒绝请求**（主流程的一部分） |
| 共同点 | 两者共用 `token_tracker.py::_record_usage` 一个入口（L54-98，同一函数内先落库后计预算） | 同左 |

### 1.2 必须保留的「同源」数据流

`agent_engine.py` L382/L515/L650 的 `"usage": result.usage`（complete 事件）→ `trip_service.py` 写 `message.metadata.usage` → 被 `feedback_service.get_high_token_low_satisfaction`、`admin_service`（agent-trace）、`Chat.vue`、`eval/` 消费。**与 token_usage_logs 表零依赖，全部保留。**

---

## 2. 改动明细

### 2.1 删除文件（10 个）

| # | 文件 | 说明 |
|---|---|---|
| 1 | `trip-backend/src/models/token_usage_log.py` | ORM 模型（表 `token_usage_logs`） |
| 2 | `trip-backend/src/services/stats_service.py` | 统计 service（`get_token_stats`/`get_token_logs`） |
| 3 | `trip-backend/src/controllers/stats_controller.py` | 3 个 API：`GET /api/stats/token-usage/{summary,stats,logs}` |
| 4 | `trip-backend/src/services/agent/token_monitor.py` | 落库 + 内存环形缓冲 + 100K 单请求告警（整文件删，见 3.1 决策） |
| 5 | `trip-backend/tests/test_stats_controller.py` | 258 行 stats API 测试 |
| 6 | `trip-front/src/api/tokenUsage.ts` | 4 个 API 封装 |
| 7 | `trip-front/src/views/TokenUsage.vue` | 展示页（558 行，含 admin 高 token 区块，随页删除） |
| 8 | `trip-backend/src/services/agent/__init__.py` | 仅删 L25 import 与 L59 `__all__` 条目（文件本身保留） |

> 注：`stats_controller.py` 删除后 `main.py` L197-198 的 include_router 一并删除（见 2.2）。`tests/test_models.py`、`tests/test_agent_engine.py`、`tests/test_agent_imports.py` 非整删，见 2.2。

### 2.2 修改文件（20 个）

**后端（13 处）**

| # | 文件:行号 | 改动 |
|---|---|---|
| 1 | `src/services/agent/token_tracker.py:6` | 更新 docstring（移除 TokenUsageLog 描述） |
| 2 | `src/services/agent/token_tracker.py:57` | 更新 docstring |
| 3 | `src/services/agent/token_tracker.py:64-81` | 删除「1. 写入 token_monitor」整块（try/except 及内部 import） |
| 4 | `src/services/agent/token_tracker.py:83-98` | **保留**「2. 更新 token_budget_manager」整块（含 `_update_budget`），编号注释改为「1.」 |
| 5 | `src/services/agent/agent_engine.py:24` | 删除 `from src.services.agent.token_monitor import token_monitor` |
| 6 | `src/services/agent/agent_engine.py:366-376` | 删除 chat 路径 token_monitor.record 块（L366 起至对应 `}))`） |
| 7 | `src/services/agent/agent_engine.py:501-512` | 删除 recommend 路径 token_monitor.record 块 |
| 8 | `src/services/agent/agent_engine.py:623-631` | 删除 recommend_variants 路径 token_monitor.record 块 |
| 9 | `src/main.py:197-198` | 删除 stats_router import 与 include_router |
| 10 | `src/models/user.py:77` | 删除 `token_logs = relationship("TokenUsageLog", ...)` |
| 11 | `src/models/conversation.py:60` | 删除 `"TokenUsageLog"` 关系字符串引用（`token_logs` 相关行） |
| 12 | `create_tables.py:18` | 删除 `from src.models.token_usage_log import TokenUsageLog` |
| 13 | `src/services/tasks/post_chat.py:27,38` | 删除 noqa import 及注释 |
| 14 | `src/services/tasks/wiki_fetch.py:28,39` | 同上 |

**脚本（3 处，防止 ImportError）**

| # | 文件:行号 | 改动 |
|---|---|---|
| 15 | `scripts/migrate_mysql_to_pg.py:44` | 迁移表清单删除 `"token_usage_logs"` |
| 16 | `scripts/ingest_spot_docs.py:47` | 删除 noqa import（保留 L36 注释或同步删除） |
| 17 | `scripts/pgvector_reindex.py:36`、`scripts/fetch_wiki.py:567`、`scripts/e2e_m1_chroma_sync.py:96` | 删除 noqa import |

**测试（3 处）**

| # | 文件:行号 | 改动 |
|---|---|---|
| 18 | `tests/conftest.py:23,35` | 删除 TokenUsageLog import |
| 19 | `tests/test_models.py:16,494-524` | 删除 import 与 `TestTokenUsageLogModel` 类 |
| 20 | `tests/test_agent_engine.py:198-200` | 删除 `TestTokenMonitor` 类（L197 注释块起至类结束） |
| 21 | `tests/test_agent_imports.py:59-64` | 删除 `test_token_monitor_module` 方法 |

**前端（4 处）**

| # | 文件:行号 | 改动 |
|---|---|---|
| 22 | `trip-front/src/router/index.ts:66-70` | 删除 `/token-usage` 路由对象 |
| 23 | `trip-front/src/views/Home.vue:168-171` | 删除 Token 用量 action-card 卡片 |
| 24 | `trip-front/src/components/layout/Sidebar.vue:33` | 删除 `{ path: '/token-usage', label: 'Tokens', icon: '📊' }` 菜单项 |

**文档**

| # | 文件 | 改动 |
|---|---|---|
| 25 | `README.md:101` | 删除 `/api/stats/token-usage/summary` API 条目 |
| 26 | `docs/backend-comparison.md`、`docs/migration-architecture.md`、`docs/migration-prd.md` | 描述性引用后置处理（本迭代不做，见 3.2） |

---

## 3. 技术决策

### 3.1 token_monitor.py 整文件删除（含 100K 告警）

`TokenMonitor` 仅被 3 处消费：`token_tracker.py`、`agent_engine.py`、测试。其内存环形缓冲（`get_recent/get_stats`）与 100K 告警无任何产品/接口消费，且监控类职责不属于 PRD 保留范围。**决策：整文件删除**；若后续仍需单请求超限告警，应在 `token_budget.py` 侧另行立项，不在本迭代引入。

### 3.2 docs/ 描述性文档后置

docs/ 中 10+ 处 token-usage 描述均为历史技术文档（migration 系列为历史快照，不应篡改）。**决策：不修改历史文档**，仅更新 README.md（对外 API 清单）。

### 3.3 数据库表不 DROP

`Base.metadata.create_all` 不再管理该表，但**存量表与数据保留**（回滚友好）。如需清理数据，运维侧手动 `DROP TABLE token_usage_logs;`，不在代码中执行。

### 3.4 settings.token_budget_user/global 保留

删除后成死配置，但删除会扩大 diff 面且与预算语义混淆。**决策：保留**，单独清理项不入本迭代。

### 3.5 token_tracker.py 的 callback 注入不变

`config/llm.py:197-198` 的 `callbacks=[token_tracker]` 注入**不动**——budget 计数仍依赖该 callback（`on_llm_end` → `_record_usage` → budget 分支）。`LLMContext`（contextvars）同理保留。

---

## 4. 不用改动的范围（保留清单）

> 以下代码**本迭代一律不动**，评审时对照此表防止误删（尤其名字带 "token/usage" 的项）。

### 4.1 后端保留项

| 文件 | 保留原因（证据） |
|---|---|
| `src/services/agent/token_budget.py` | `TokenBudgetManager` 内存单例，429/503 守卫的数据源，不依赖 DB |
| `src/middleware/token_budget_guard.py` | 挂在 `chat_controller.py:62`、`trip_controller.py:37/145` 的 Depends 守卫 |
| `src/services/agent/token_tracker.py`（仅删落库块） | budget 计数唯一入口（L83-98） |
| `src/config/llm.py:197-198` | callback 注入（budget 依赖） |
| `src/services/agent/agent_engine.py:382/515/650` | complete 事件 `"usage": result.usage` → message.metadata 链路 |
| `src/services/feedback_service.py::get_high_token_low_satisfaction` + `feedback_controller.py:170` | 查 `feedbacks` + `messages.metadata.usage`，零依赖统计表 |
| `src/services/admin_service.py` + `admin_controller.py`（agent-trace） | 同上（metadata 链路） |
| `src/services/trip_service.py:183` | `metadata = {"usage": usage}` 写入 |
| `src/utils/tokens.py`、`src/services/summary_service.py` | 对话窗口压缩估算，与统计无关 |
| `src/middleware/rate_limiter.py`、`concurrency_guard`、JWT 全链路 | 独立功能 |
| `tests/test_middleware.py::TestTokenBudgetGuard`、`tests/test_chat_controller.py`（dependency override）、`tests/test_agent_engine.py`（TestTokenBudgetManager 部分） | 预算守卫测试，必须全绿 |

### 4.2 前端保留项

| 文件 | 保留原因 |
|---|---|
| `src/views/Chat.vue:17,27`（TokenUsage interface） | SSE complete 事件的 usage 展示，数据来自事件流 |
| `src/views/AdminFeedbackDashboard.vue`（含 usage/cacheHitRate 聚合 L98-116, 284-338） | 独立入口，数据源 metadata |
| `src/views/AdminTrace.vue` | 数据源 metadata |
| `src/api/trace.ts` | 打 `/admin/agent-trace/*`，与统计接口无关 |

### 4.3 其他保留项

| 项 | 说明 |
|---|---|
| `eval/` 目录 | `event.usage` 来自 SSE complete 事件，不依赖 stats API |
| `test.db` 等存量库中 token_usage_logs 表 | 不 DROP（决策 3.3） |
| `.github/` CI 工作流 | 若引用 stats 相关测试，随测试删除自动失效，无需改动 |

---

## 5. 实施顺序与验证

### 5.1 分步计划（建议 3 个 commit）

| 步骤 | 内容 | 验证 |
|---|---|---|
| **C1 后端核心** | 删模型/service/controller/token_monitor + main.py + agent_engine + token_tracker 落库块 + 模型关系 + create_tables + scripts/tasks noqa | `python -c "import src.main"`；启动冒烟；`pytest tests/test_middleware.py tests/test_chat_controller.py` |
| **C2 测试清理** | conftest / test_models / test_stats_controller / test_agent_engine / test_agent_imports | `pytest` 全量通过 |
| **C3 前端 + 文档** | router / Home / Sidebar / tokenUsage.ts / TokenUsage.vue / README | `pnpm build`；`pnpm lint`（如有）；grep 兜底 |

### 5.2 验收命令（对齐 PRD 第 4 节）

```bash
# 后端：全量测试 + 无残留引用（docs/ 除外）
cd trip-backend && pytest -q
rg -n "token_usage_log|TokenUsageLog|token_monitor|stats_service|token-usage" src scripts tests create_tables.py

# 前端：构建 + 无残留引用
cd trip-front && pnpm build
rg -n "token-usage|TokenUsage|tokenUsage" src

# 运行时冒烟（对话主流程 + 预算守卫）
# 1) 正常对话 → SSE 流式输出正常，complete 事件含 usage
# 2) 人工触发 user 超限 → 429（token_budget.py 阈值 50_000）
# 3) GET /api/stats/token-usage/* → 404
# 4) 前端 /token-usage → 404 页
```

---

## 6. 风险与回滚

| # | 风险 | 缓解 | 回滚 |
|---|---|---|---|
| R1 | token_tracker.py 误删 budget 分支 → 守卫失效 | C1 提交后立即跑 TestTokenBudgetGuard | git revert C1 |
| R2 | mapper 关系链断裂 → arq worker/scripts 启动报 InvalidRequestError | 删模型前确认 7 处 noqa import 同 commit 清理；启动 worker 验证 | git revert C1 |
| R3 | 前端悬空引用 → build 失败 | grep 兜底 + pnpm build | git revert C3 |
| R4 | 误删 metadata usage 链路（R4 表） | 评审对照第 4 节保留清单 | git revert |
| R5 | 存量表无人管理（孤儿表） | 决策 3.3 已明确，非缺陷 | — |

---

## 7. 附录：验证过的代码位置速查

| 关键位置 | 内容 |
|---|---|
| `token_tracker.py:54-98` | `_record_usage`：L64-81 落库（删），L83-98 budget（留） |
| `token_monitor.py:40-75` | `record()`：环形缓冲 + 100K 告警 + 落库（整删） |
| `token_monitor.py:77-109` | `_save_to_db` 独立 async session（随文件删除） |
| `agent_engine.py:366-376 / 501-512 / 623-631` | 3 处 record 块（删）；L382/515/650 usage 事件（留） |
| `stats_controller.py:13-100` | `router = APIRouter(prefix="/stats")` 3 个 endpoint |
| `main.py:197-198` | include_router(stats_router, prefix="/api") |
| `user.py:77` / `conversation.py:60` | token_logs relationship |
| `tests/test_agent_imports.py:59-64` | token_monitor 导入冒烟测试 |
| `tests/test_agent_engine.py:197-230` | TestTokenMonitor 类 |
| 前端 4 处 | router:66-70 / Home:168-171 / Sidebar:33 / TokenUsage.vue 整文件 |
