# Java 迁移实施准备总结

> **日期**：2026-08-01
> **状态**：文档已读完，准备开始实施

---

## 一、迁移目标

将 `trip-backend/`（Python FastAPI）完整重构为 Java 21 + Spring Boot 3.3，**功能 1:1 复刻，前端零改动，数据零迁移**。

**新工程路径**：`trip-backend-java/`

---

## 二、已读完的核心文档

| 文档 | 大小 | 主要内容 |
|------|------|---------|
| `migration-prd-java.md` | 35KB | 产品需求：43 个 API 端点、SSE 协议、Agent 能力、RAG 检索、验收标准（7 大维度） |
| `java-migration-technical-design.md` | 47KB | 技术方案：32 个组件选型、关键设计取舍（T1-T8）、核心类设计、数据兼容方案 |
| `java-migration-execution-plan.md` | 55KB | 执行计划：33 个任务（A1-E5）、依赖拓扑图、并行建议、关键路径 ~42 人日 |

---

## 三、当前项目状态（Python 侧）

### 技术栈
- **后端**：FastAPI (Python 3.12+)
- **数据库**：PostgreSQL 16 + pgvector
- **Redis**：7（缓存 + 任务队列 + 流续传）
- **AI**：LangChain/LangGraph + DeepSeek/Kimi/Agnes 多 provider
- **前端**：Vue 3 + TypeScript + Naive UI（**本次不改**）

### 项目规模
- **12 张表**：roles/users/password_resets/trips/conversations/messages/spots/spot_docs/feedbacks/agent_steps/token_usage_logs
- **43 个 API 端点**（含管理后台）
- **49 个 pytest 测试文件** + 6 个 e2e 流程
- **~150 个 Python 源文件**

---

## 四、核心设计决策（Java 侧）

### 技术选型

| 决策点 | 选择 | 关键理由 |
|--------|------|---------|
| **Web 层** | WebMVC + 虚拟线程 | 命令式代码与 Python 1:1 映射；SSE 手动写帧可控 |
| **ORM** | JPA(标量) + JdbcTemplate(向量/全文) | 向量走原生 SQL，HNSW 索引零改动复用 |
| **LLM 接入** | langchain4j 协议 + 自研编排 | 先 spike 验证流式 tool_calls + usage 提取能力 |
| **任务队列** | 自研 Redis List 队列 | 语义与 arq 完全对齐；Redis 不可用降级内存 |
| **Embedding** | ONNX Runtime（首选） | 离线推理；余弦一致性 ≥0.999 放行；旁路 Python 服务为备选 |
| **SSE 输出** | 手动写帧 | 100% 控制帧格式与 flush 时机；天然规避缓冲 |
| **高德 MCP** | ProcessBuilder + 手写 JSON-RPC | 完全复刻 Python stdio 子进程行为 |
| **限流/守卫** | 自研 Filter 链 | 顺序与 Python 中间件链完全对应 |

### 关键架构约束

1. **`ddl-auto=none`**：绝不由 Hibernate 改表，直接连现有 PG
2. **向量走原生 SQL**：`1 - (embedding <=> CAST(:vec AS vector))`，JPA 实体 `@Transient`
3. **SSE 不缓冲**：GZip 中间件对 SSE 路径跳过；每次事件后 `flush()`
4. **异常映射不对称**：auth/限流/守卫抛 `HTTPException` → `{"detail":...}`；业务 `AppException` → Format A/B
5. **JWT 不对称**：缺头 403 / 坏或过期 401（HTTPBearer 默认）
6. **并发守卫**：全局 `Semaphore(10)` + 每用户 `Semaphore(1)`，非阻塞 429；SSE 流 `finally` 释放
7. **Redis key 格式逐字对齐**：便于对拍验证

---

## 五、任务拆分（33 个任务）

### 阶段 A：工程基建（A1-A4，~5 天）
- **A1**：工程骨架 + 配置 + 日志 + 异常映射 + 健康检查
- **A2**：中间件链（RequestID/Prometheus/GZip/CORS）+ RateLimiter 组件
- **A3**：数据层：12 表 JPA + JSONB + vector 原生 SQL + password_resets 补建
- **A4**：Redis 客户端 + 4 缓存组件

### 阶段 B：用户/CRUD（B1-B7，~9 天）
- **B1**：认证 7 端点
- **B2-B6**：会话、知识库、反馈、统计、通勤 CRUD
- **B7**：幂等 + 并发守卫 + token 预算守卫

### 阶段 C：RAG（C0-C4，~7.5 天）
- **C0**：TaskQueue 双后端
- **C1**：Embedder + Reranker ONNX 加载
- **C2**：检索流水线（双路召回）
- **C3**：四路召回 + credibility 重排
- **C4**：embedding_sync 任务

### 阶段 D：Agent 核心（D1-D12，~17 天）
- **D1**：LLM Gateway spike（前置风险点）
- **D2-D12**：Token 记账、SSE 基建、ChatAgent、工具层、MCP、Orchestrator、AgentEngine、技能系统、推荐链路、后处理

### 阶段 E：运维面（E1-E5，~5.5 天）
- **E1**：告警系统
- **E2**：健康检查 + docker-compose
- **E3**：压测
- **E4**：端到端联调
- **E5**：CI 流水线

**关键路径**：A1→A2→A3→C1→C2→C3→D5→D7→D8→D11→E4 ≈ 24~26 人日

---

## 六、前置调查清单（实施前必做）

### 6.1 现有库实测（对 A3 至关重要）

```sql
-- 1. 验证 12 表存在
SELECT table_name FROM information_schema.tables
WHERE table_schema='public' AND table_type='BASE TABLE'
ORDER BY table_name;

-- 2. 验证 password_resets 表状态（是否已存在？DDL 是否一致）
\d password_resets

-- 3. 验证 HNSW 索引参数
SELECT indexname, indexdef FROM pg_indexes
WHERE tablename IN ('spots', 'spot_docs')
AND indexdef LIKE '%hnsw%';

-- 4. 验证向量抽样（用于 cosine 一致性回归）
SELECT id, name, embedding::text FROM spots
WHERE embedding IS NOT NULL LIMIT 5;

-- 5. 验证现有数据量
SELECT 'users' AS tbl, COUNT(*) FROM users UNION ALL
SELECT 'spots', COUNT(*) FROM spots UNION ALL
SELECT 'trips', COUNT(*) FROM trips UNION ALL
SELECT 'conversations', COUNT(*) FROM conversations;
```

### 6.2 bcrypt 互认验证

```python
# 用 Python 生成测试哈希，验证 Java 侧 jBCrypt 能识别
import bcrypt
password = "test123"
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
print(hashed.decode())  # 带到 Java 侧测试 BCrypt.checkpw()
```

### 6.3 LLM Spike（D1 前置）

验证 langchain4j 1.x 对三个关键点的支持：
1. **流式 tool_calls delta 累积**：能否在流式过程中逐步累积完整工具调用
2. **末帧 usage 提取**：`include_usage` + `cachedTokens` 能否取出
3. **中文 tool schema**：description 字段能否正确下发

### 6.4 ONNX 导出验证（C1 前置）

- [ ] 导出 bge-small-zh-v1.5 为 ONNX（需确认是否已有导出）
- [ ] 移植 tokenizer（WordPiece，查询前缀必须逐字保留）
- [ ] 抽样 50 条现有库 spots.embedding，与 Java 复算向量做余弦一致性回归（目标 ≥0.999）

### 6.5 环境准备

- [ ] 确认 Java 21 已安装（`java -version`）
- [ ] 确认 Maven 3.9+ 已安装（`mvn -version`）
- [ ] 确认能访问现有 PostgreSQL + Redis
- [ ] 准备独立的 `trip-backend-java/` 工程目录
- [ ] 确认 `.env` 文件可读取（含数据库连接、API Key、高德 Key）

---

## 七、下一步行动（待确认）

根据执行计划，建议按以下顺序启动：

### **立即启动（无前置依赖）**

1. **调查现有库状态**（§6.1）— 确认 12 表现状、HNSW 索引参数、password_resets 表是否存在
2. **创建 `trip-backend-java/` 工程骨架**（A1）— Spring Boot 3.3 + Java 21 + 基础依赖
3. **LLM Spike**（D1 前置）— 验证 langchain4j 流式工具调用能力

### **并行启动（依赖 A1）**

4. **数据层 JPA 实体编写**（A3）— 基于 §6.1 实测结果
5. **密码哈希互认测试**（§6.2）— 确认 bcrypt rounds=12 兼容

### **关键阻塞点**

- **ONNX 导出**（C1）— 若向量精度无法对齐，需启用旁路 Python embedding 服务（备选方案 B）
- **LLM spike 失败**（D1）— 若 langchain4j 无法满足流式语义，降级自研 OpenAI 协议层

---

## 八、风险预案速查

| 风险 | 等级 | 触发信号 | 预案 |
|------|------|---------|------|
| langchain4j tool_calls 格式差异 | 🔴 高 | spike 阶段 tool_calls delta 累积不全 | 编排层与协议层解耦；降级自研协议层 |
| ONNX 精度漂移 | 🔴 高 | 余弦一致性 <0.999 | 启用旁路 Python embedding 服务；配置开关隔离四路/双路 |
| SSE 被中间件缓冲 | 🔴 高 | 心跳/断线联调失败 | 手动写帧 + GZip 跳过 + `flush()` |
| pgvector 与 ORM 冲突 | 🔴 高 | JPA 启动报 vector 类型未知 | 实体 `@Transient`；向量 SQL 收敛在 JdbcTemplate |
| 契约细节陷阱 | 🟡 中 | 403/401 不对称、X-RateLimit-Reset 等不符 | 例外清单整理为契约测试用例表 |
| 四路召回改变检索行为 | 🔴 高 | top-N 结果变化、指标波动 | 配置开关隔离；检索评估 + 对话 eval 双回归 |

---

## 九、验收总览（8 大量化目标）

| # | 目标 | 验证方式 |
|---|------|---------|
| G1 | API 契约 100% 兼容 | 43 端点 × 方法/路径/参数/响应体/错误码 |
| G2 | 前端零改动可用 | 仅切换 VITE_API_BASE |
| G3 | 数据零迁移 | 直接连现有 PG，12 表 schema 兼容 |
| G4 | 功能行为对等 | chat/recommend/modify/patch 编排对拍 |
| G5 | 测试对等 | 49 pytest 测试语义等价迁移 |
| G6 | 评估不倒退 | eval fixture 通过率、Hit@K/MRR ≥ 基线 |
| G7 | 性能不劣于基线 | 登录 QPS ≥ 6.0、SSE 流 15–21s |
| G8 | 可观测性对等 | Prometheus 4 类指标 + x-request-id 全链路 |

---

## 十、待确认问题

在正式启动实施前，需要与主理人确认以下问题：

1. **现有库 password_resets 表状态**：是否已存在？DDL 是否与 `models/password_reset.py` 一致？
2. **ONNX 导出资源**：bge-small-zh-v1.5 和 bge-reranker-base 的 ONNX 模型是否已导出？或需要现在开始导出？
3. **bcrypt 互认测试**：现有库用户密码是否可用（Python bcrypt 12 rounds）？
4. **并行策略**：单人实施（~9 周）还是双人并行（~5 周）？
5. **实施起点**：从 A1（工程骨架）开始，还是先完成 §6 前置调查？

---

**准备就绪，等待确认后开始实施。**
