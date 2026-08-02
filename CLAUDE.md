# Claude Code 全局指令 — Trip 项目

> **生效日期**：2026-08-01
> **适用范围**：`/Users/wang/Documents/trip`（Trip AI 智能旅行规划系统）

---

## 1. 核心约束

### 1.1 双版本并行原则

- **Java 版本与 Python 版本同时存在，互不冲突**
  - Python 版本：`trip-backend/`（FastAPI，持续维护）
  - Java 版本：`trip-backend-java/`（Spring Boot 3.3，重构中）
- 两个版本**并行运行**，前端可通过 `VITE_API_BASE` 切换
- **数据共享**：Java 版本直接连接现有 PostgreSQL + Redis，不做数据迁移
- **前端零改动**：`trip-front/` 不因 Java 版本迁移动任何代码

### 1.2 Git 提交流程

- **每完成一个小任务立即 commit**
  - "小任务"定义为：单个文件创建/修改、单个功能点验证通过、单个阶段验收完成
  - 粒度建议：每个任务 commit 不超过 5-10 个文件变更
- **不推送到远端仓库**
  - 所有提交仅保留在本地
  - 等待进一步指令后再决定推送时机
- **Commit message 规范**
  - 格式：`[阶段X][任务Y] 简要描述`（如 `[A1] 工程骨架 + 配置 + 日志 + 异常映射`）
  - 关联验收条目（如 `验收: 1.6, 1.8`）

---

## 2. 项目目标

**Java 版本核心目标**：
- 功能 1:1 复刻 Python 版（43 个 API 端点、SSE 协议、Agent 编排、RAG 检索）
- 验收标准：8 大量化目标（API 契约兼容、性能不劣于基线、评估不倒退等）
- 总工期：关键路径 ~42 人日（详见 `docs/java-migration-execution-plan.md`）

---

## 3. 技术栈（Java 版本）

| 层级 | 技术 |
|------|------|
| 语言/框架 | Java 21 + Spring Boot 3.3（WebMVC + 虚拟线程） |
| ORM | Spring Data JPA（标量）+ JdbcTemplate（向量/全文） |
| 数据库 | PostgreSQL 16 + pgvector（`ddl-auto=none`，直连现有库） |
| 缓存 | Redis 7（Lettuce），双后端（Redis 优先 / 内存降级） |
| AI 接入 | langchain4j 1.x（协议层）+ 自研编排 |
| Embedding | ONNX Runtime（bge-small-zh-v1.5） |
| Reranker | ONNX Runtime CrossEncoder（bge-reranker-base） |
| 任务队列 | 自研 Redis List 队列 + @Async 内存降级 |
| MCP | ProcessBuilder + 手写 JSON-RPC 2.0（高德地图） |
| 监控 | Micrometer + Prometheus + Logback（MDC） |

---

## 4. 关键设计约束

- **`ddl-auto=none`**：绝不由 Hibernate 改表，直接复用现有 PostgreSQL schema
- **向量走原生 SQL**：`1 - (embedding <=> CAST(:vec AS vector))`，JPA 实体 `@Transient`
- **SSE 手动写帧**：100% 控制帧格式与 flush 时机，避免中间件缓冲
- **异常映射不对称**：
  - auth/限流/守卫抛 `HTTPException` → `{"detail":...}`（FastAPI 默认）
  - 业务 `AppException` → Format A/B（`/api/trip/recommend` 前缀判定）
- **JWT 不对称**：缺头 403 / 坏或过期 401（HTTPBearer 默认行为）
- **Redis key 格式逐字对齐**：便于与 Python 版对拍验证

---

## 5. 任务管理

- **执行计划**：`docs/java-migration-execution-plan.md`（33 个任务 A1-E5）
- **技术设计**：`docs/java-migration-technical-design.md`
- **产品需求**：`docs/migration-prd-java.md`
- **实施准备总结**：`docs/java-migration-implementation-readiness.md`

---

## 6. 前置任务清单（未完成）

- [x] **§6.1 现有库实测**：验证 12 表现状、HNSW 索引参数、password_resets 表状态 ✅
- [ ] **§6.2 bcrypt 互认测试**：确认 Java jBCrypt 12 rounds 与 Python 现有密码哈希互认
- [ ] **§6.3 LLM Spike**：验证 langchain4j 1.x 流式 tool_calls + usage 提取能力
- [ ] **§6.4 ONNX 导出验证**：bge-small-zh-v1.5 和 bge-reranker-base ONNX 导出 + tokenizer 移植
- [x] **A1-A4 工程基建** ✅
- [x] **B1-B7 用户/CRUD（11 表 + 43 端点）** ✅
- [x] **C0 TaskQueue + C1 Embedder/Reranker 接口** ✅
- [x] **D1 LLM Gateway + Provider 路由** ✅
- [x] **D2 Token 记账三件套** ✅
- [x] **D3 SSE 基建（SseWriter + StreamStore + 断点续传）** ✅
- [x] **P0/P1 问题修复（16 项）** ✅

---

## 7. 验收总览（8 大量化目标）

| # | 目标 | 验证方式 |
|---|------|---------|
| G1 | API 契约 100% 兼容 | 43 端点 × 方法/路径/参数/响应体/错误码 |
| G2 | 前端零改动可用 | 仅切换 `VITE_API_BASE` |
| G3 | 数据零迁移 | 直连现有 PG，12 表 schema 兼容 |
| G4 | 功能行为对等 | chat/recommend/modify/patch 编排对拍 |
| G5 | 测试对等 | 49 pytest 测试语义等价迁移 |
| G6 | 评估不倒退 | eval fixture 通过率、Hit@K/MRR ≥ 基线 |
| G7 | 性能不劣于基线 | 登录 QPS ≥ 6.0、SSE 流 15–21s |
| G8 | 可观测性对等 | Prometheus 4 类指标 + x-request-id 全链路 |

---

**创建时间**：2026-08-01
**最后更新**：2026-08-01
