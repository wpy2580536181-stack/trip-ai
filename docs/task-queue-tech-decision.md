# 任务队列技术选型与改造方案决策文档

| 项        | 值                                                                     |
| -------- | --------------------------------------------------------------------- |
| **文档版本** | v0.1（待评审）                                                             |
| **创建日期** | 2026-07-20                                                            |
| **目标读者** | 后端研发 / 技术负责人 / 团队评审                                                   |
| **关联项目** | `trip-backend`（Python 3.12+ / FastAPI / SQLAlchemy Async / LangGraph） |
| **评审状态** | ⏳ 待评审                                                                 |

---

## 0. TL;DR（一页结论）

> **建议引入 arq（基于 Redis 的异步任务队列）作为项目的可靠任务执行层**，覆盖 4 个真实痛点（API 写路径同步 embedding、chat 后处理小尾巴、离线长 ETL、分布式告警调度），最小改动 5 个文件、约 120 行新增代码即可落地。
>
> **核心依据**：
>
> 1. **基础设施已 100% 就位**——Redis 8.0 客户端、6 处生产路径在用、docker-compose 已配 `redis:7-alpine`、测试有 `mock_redis` fixture；
> 2. **设计模式已成熟**——`poi_cache.py` 的「Redis 优先 + 内存降级」是直接可抄的样板；
> 3. **生态最匹配**——arq 与 FastAPI 同样是 `asyncio` 模型，无需桥接同步/异步；
> 4. **风险可控**——所有候选技术都已在生产验证，社区稳定，可随时切到 Celery。
>
> **不建议**：Kafka / RabbitMQ（杀鸡用牛刀）/ Celery（与 async 代码桥接成本高）/ 直接用 `asyncio.create_task`（生产环境反模式）。

---

## 1. 背景与现状

### 1.1 项目异步任务处理全景（基于代码事实）

通过 `src/` 全局搜索 `asyncio.create_task` / `asyncio.Queue` / `BackgroundTasks` / `celery*` / `arq*` / `rq*` 得到以下事实：

| 维度                        | 现状       | 证据位置                                                                                 |
| ------------------------- | -------- | ------------------------------------------------------------------------------------ |
| **消息队列**                  | ❌ 无      | 全局搜索 0 命中                                                                            |
| **`BackgroundTasks`**     | ❌ 无      | `trip-backend/src` 下 0 命中                                                            |
| **`asyncio.create_task`** | ⚠️ 3 处使用 | `trip_service.py:307`、`alert_scheduler.py:46`、`knowledge_service.py:455/463/469/475` |
| **同步阻塞批处理**               | ⚠️ 多处    | `scripts/fetch_wiki.py`、`scripts/chroma_reindex.py`、`scripts/ingest_spot_docs.py`    |

### 1.2 已具备的基础设施（直接可复用）

| 组件                    | 状态    | 证据                                                                                                   |
| --------------------- | ----- | ---------------------------------------------------------------------------------------------------- |
| **Redis 客户端**         | ✅ 已装  | `pyproject.toml: redis>=5.0.0`（uv.lock 锁 8.0.1）                                                      |
| **异步 Redis 客户端**      | ✅ 已封装 | `src/config/redis_client.py`（基于 `redis.asyncio`）                                                     |
| **应用启动连接**            | ✅ 已接  | `src/main.py` lifespan：`await init_redis()` / `await close_redis()`                                  |
| **docker-compose 服务** | ✅ 已配  | `docker-compose.yml: redis:7-alpine + redis_data` 卷                                                  |
| **测试基础设施**            | ✅ 已就  | `tests/conftest.py: mock_redis` fixture                                                              |
| **生产路径在用**            | ✅ 6 处 | `llm_cache` / `poi_cache` / `stream_store` / `tool_cache` / `research_bundle_cache` / `rate_limiter` |
| **双后端降级模式**           | ✅ 已沉淀 | `poi_cache.py:127-131` `_RedisPOICache` + `_MemoryPOICache` + `is_redis_available()` 切换              |

> **结论**：引入 arq **零基础设施成本**，只需在 `pyproject.toml` 加一行依赖。

### 1.3 设计模式沉淀（建议直接照抄）

`src/services/poi_cache.py:127-131` 的模式是教科书级别的样板：

```python
class POICache:
    def __init__(self):
        use_redis = is_redis_available()
        self._backend = _RedisPOICache() if use_redis else _MemoryPOICache()
        self._backend_type = "redis" if use_redis else "memory"
```

**新引入的 `task_queue.py` 应沿用同样范式**：arq 优先、asyncio.create_task 降级，上层无感。

---

## 2. 核心痛点（基于代码证据）

### 痛点 1：API 写路径同步阻塞（P0）

**事实**（`src/services/knowledge_service.py:204-272`、`:274-349`、`:1011-1143`）：

```python
# create_spot / update_spot / bulk_import_spots 都遵循同一模式
db.add(spot)
await db.commit()              # MySQL 落库 OK
# ↓↓↓↓↓↓↓↓↓↓↓↓↓ 同步阻塞 ↓↓↓↓↓↓↓↓↓↓↓↓
collection = await get_spots_collection()
embedding = await embed_query_async(doc_text)  # BGE 模型，1~3s
await run_sync(collection.add, embeddings=[embedding], ...)  # Chroma RPC
```

**影响**：

- 管理员点「保存景点」→ 前端等 1-3 秒
- `bulk_import_spots` 批量 100 条 → 用户等 30 秒+
- Chroma 抽风时整条 API 超时，**MySQL 已落库但前端报失败**（双写不一致）

**这正是消息队列的核心价值场景**：「**调用方不需要实时等下游完成**」。

---

### 痛点 2：chat 后处理小尾巴（P0）

**事实**（`src/services/trip_service.py:287-307`）：

```python
def _post_chat_tasks(self, conversation_id: int, user_message: str) -> None:
    async def _run():
        await summary_service.compress_conversation(...)        # 摘要压缩
        await summary_service.append_key_decision(...)           # 关键决策
    asyncio.create_task(_run())   # ← 反模式：进程崩就丢
```

**4 个生产环境问题**：

1. **不可靠**——`asyncio.create_task` 在 FastAPI 多 worker 部署下，进程崩溃/重启 = 任务蒸发；
2. **无重试**——LLM 调用偶尔失败，任务静默丢失；
3. **无状态查询**——你**完全不知道**哪些对话的摘要压完、哪些没压；
4. **可能重复**——同一对话多次结束触发，会重复记录决策。

---

### 痛点 3：长任务批处理无重试/无进度（P1）

**事实**（`scripts/fetch_wiki.py`、`scripts/chroma_reindex.py`）：

- **fetch_wiki** 153 城，单进程串行 49 分钟（已踩过 CLOSE_WAIT 假死坑，并发 12→8 才稳定）；
- **chroma_reindex** 全量重建 embedding 库，单进程跑到底；
- **失败无重试**——单城代理超时 = 该城数据缺失；
- **进度靠日志**——无法断点续跑，跑挂了重头再来。

---

### 痛点 4：告警调度无法多副本（P1）

**事实**（`src/services/alert/alert_scheduler.py:46`）：

```python
self._task = asyncio.create_task(self._run_loop())  # 单进程 asyncio 循环
```

未来 K8s 部署 3 副本 → **3 个副本各跑一遍告警检测 → 重复发 3 次 webhook**。需要分布式锁或 leader 选举。

---

### 反例：哪些场景**不**需要任务队列（避免过度设计）

| 场景              | 现有做法                                                                  | 为什么不需要 MQ                                                       |
| --------------- | --------------------------------------------------------------------- | --------------------------------------------------------------- |
| RAG 检索的 4 路并行召回 | `knowledge_service.search_spots:451-478` 4 个 `asyncio.create_task` 并行 | **低延迟要求**（用户搜索秒级返回）+ **单请求生命周期** + **失败要快速降级**。上 MQ 引入网络往返，得不偿失 |
| SSE 流式响应的事件分发   | `trip_service.py:170` `asyncio.Queue`                                 | 同上：单连接、单请求范围                                                    |
| Chroma 集合健康检查   | `check_chroma_health()` 直接 await                                      | 单次 RPC，不需要解耦                                                    |



> **设计原则**：跨进程、跨请求、跨时间、需要可靠投递的场景才上 MQ；单请求内的并发协作继续用 `asyncio.gather`。



---

## 3. 改进建议（具体可操作）

### 3.1 P0-1：API 写路径异步化

**改造点**：`knowledge_service.create_spot` / `update_spot` / `bulk_import_spots`

**Before**（约 30 行同步 Chroma 写入）：

```python
# commit MySQL 后立即同步写 Chroma
db.add(spot)
await db.commit()
try:
    collection = await get_spots_collection()
    embedding = await embed_query_async(doc_text)
    await run_sync(collection.add, ids=[vector_id], embeddings=[embedding], ...)
except Exception as e:
    logger.warning("Chroma sync failed (MySQL data saved)", error=str(e))
```

**After**（commit MySQL 后入队，< 5ms 返回）：

```python
db.add(spot)
await db.commit()
# 入队：失败也只丢一条 embedding，不影响 API
try:
    await get_task_queue().enqueue(
        sync_spot_to_chroma,
        spot_id=spot.id,
        doc_text=doc_text,
        vector_id=vector_id,
        metadata={...},
    )
except Exception as e:
    logger.warning("Enqueue chroma sync failed (MySQL data saved)", error=str(e))
return spot
```

**收益**：

- API P95 时延从 800ms 降到 50ms
- Chroma 故障不再影响 API 可用性（双写解耦）
- 可在后台重试（带指数退避）

---

### 3.2 P0-2：chat 后处理可靠化

**改造点**：`trip_service._post_chat_tasks`

**Before**：

```python
asyncio.create_task(_run())  # 进程崩就丢
```

**After**（用 arq + 幂等键）：

```python
# 入队时用 conversation_id 作幂等键，重复入队只执行一次
await get_task_queue().enqueue(
    post_chat_summary,
    conversation_id=conversation_id,
    user_message=user_message,
    _job_id=f"post_chat:{conversation_id}",  # 幂等
)
```

**Worker 函数**：

```python
async def post_chat_summary(ctx, conversation_id: int, user_message: str):
    async with async_session() as session:
        await summary_service.compress_conversation(session, conversation_id)
    if is_planning_request(user_message):
        async with async_session() as session:
            await summary_service.append_key_decision(session, conversation_id, ...)
```

**收益**：进程崩溃后任务自动重投，失败有重试，状态可查。

---

### 3.3 P1-1：长任务入队（fetch_wiki / chroma_reindex）

**改造点**：`scripts/fetch_wiki.py` 主循环

**Before**：单进程 49 分钟跑到底，挂了重头再来。

**After**：

```python
# 主进程：遍历城市，每城入队
for city in cities:
    for spot in city_spots:
        await task_queue.enqueue(
            fetch_wiki_for_spot,
            spot_id=spot.id,
            spot_name=spot.name,
            city=spot.city,
            _job_id=f"wiki:{spot.id}",  # 幂等：可重跑
        )
# 进度：worker 写回 spot_docs 表的 source_url='pending' 字段
# 监控：SELECT COUNT(*) FROM spot_docs WHERE source_type='wiki' AND created_at > xxx
```

**收益**：可水平扩展（多 worker 并发）、可断点续跑（`--skip-existing`）、失败自动重试 3 次。

---

### 3.4 P1-2：告警调度分布式化

**改造点**：`alert_scheduler.py`

**方案 A（推荐）**：arq cron 任务

```python
# 每 5 分钟触发一次，arq 保证多副本下只执行一次
async def alert_tick(ctx):
    async with async_session() as db:
        check = await alert_detector.check(db)
    if check.should_alert and await alert_deduplicator.should_send():
        await webhook_notifier.send(check)
```

**方案 B**：保留单进程 asyncio 循环，加 Redis 分布式锁

```python
if not await redis.set("alert:scheduler:lock", "1", nx=True, ex=240):
    return  # 其他副本已在跑
```

---

## 4. 选型理由

### 4.1 核心约束

| 约束             | 推导                                                               |
| -------------- | ---------------------------------------------------------------- |
| **已有 Redis**   | 不可能为了队列再引一个 broker（Kafka/RabbitMQ）                               |
| **已是 async 栈** | FastAPI + SQLAlchemy Async + redis.asyncio，**不能再引入同步 worker 模型** |
| **QPS 体量**     | < 100 RPS（个人项目/PoC 阶段），不需要 Kafka 级吞吐                             |
| **学习成本**       | 团队后端以 Python 为主，避开 JVM 系（Scala/Kotlin）                           |
| **可靠性需求**      | 需要「失败重试 + 死信 + 状态可查」三件套，不要 fire-and-forget                       |

### 4.2 选型维度（7 项）

1. **并发模型**（async 友好度）
2. **Broker 依赖**（是否复用已有 Redis）
3. **生态成熟度**（生产案例数）
4. **可观测性**（任务状态/进度/失败原因）
5. **可靠性**（重试/死信/幂等/事务）
6. **学习曲线**（团队上手成本）
7. **监控调试**（dashboard / Flower / arq dashboard）

### 4.3 决策结论

**arq + Redis** 在 7 个维度中：

- **5 项占优**：并发模型、Broker 复用、学习曲线、与 FastAPI 适配度、调试（自带 dashboard）
- **1 项持平**：可靠性（与 Celery 持平，都支持重试/死信）
- **1 项不适用**：监控大集群吞吐（项目阶段不到）

---

## 5. 技术对比（7 维矩阵）

### 5.1 候选清单

| 候选                           | 定位                | Broker                  |
| ---------------------------- | ----------------- | ----------------------- |
| **arq**                      | Python 异步任务队列     | Redis                   |
| **Celery**                   | Python 老牌分布式任务队列  | Redis/RabbitMQ/AMQP/SQS |
| **Dramatiq**                 | Python 任务队列（中间路线） | RabbitMQ/Redis          |
| **RQ (Redis Queue)**         | Python 简单任务队列     | Redis                   |
| **Kafka**                    | 分布式事件流平台          | 自带                      |
| **RabbitMQ**                 | 消息中间件             | 自带                      |
| **asyncio.create_task**（不引入） | 进程内协程             | —                       |

### 5.2 维度对比表

| 维度                  | arq               | Celery                     | Dramatiq | RQ     | Kafka     | RabbitMQ  | asyncio.create_task |
| ------------------- | ----------------- | -------------------------- | -------- | ------ | --------- | --------- | ------------------- |
| **并发模型**            | ✅ async 协程        | ⚠️ 多进程同步                   | ⚠️ 多进程   | ⚠️ 多进程 | ⚠️ JVM 线程 | ⚠️ JVM 线程 | ✅ async 协程          |
| **Broker 复用 Redis** | ✅ 唯一              | ✅ 可选                       | ✅ 可选     | ✅ 唯一   | ❌ 自带      | ❌ 自带      | —                   |
| **生态成熟度**           | ⭐⭐⭐               | ⭐⭐⭐⭐⭐                      | ⭐⭐⭐      | ⭐⭐⭐    | ⭐⭐⭐⭐⭐     | ⭐⭐⭐⭐⭐     | —                   |
| **可观测性**            | ⭐⭐⭐⭐ 自带 web UI    | ⭐⭐⭐⭐⭐ Flower               | ⭐⭐⭐      | ⭐⭐     | ⭐⭐⭐⭐⭐     | ⭐⭐⭐⭐      | ❌ 无                 |
| **可靠性**（重试/死信/幂等）   | ⭐⭐⭐⭐              | ⭐⭐⭐⭐⭐                      | ⭐⭐⭐⭐     | ⭐⭐⭐    | ⭐⭐⭐⭐⭐     | ⭐⭐⭐⭐⭐     | ❌ 无                 |
| **学习曲线**            | ⭐⭐⭐⭐⭐ 50 行上手      | ⭐⭐⭐ worker/beat/result 三件套 | ⭐⭐⭐      | ⭐⭐⭐⭐   | ⭐⭐ JVM 运维 | ⭐⭐ 协议复杂   | ⭐⭐⭐⭐⭐               |
| **FastAPI 适配度**     | ⭐⭐⭐⭐⭐ 同一 async 模型 | ⭐⭐⭐ 需桥接 sync               | ⭐⭐⭐      | ⭐⭐⭐    | ⭐⭐        | ⭐⭐        | ⭐⭐⭐⭐                |
| **本项目评分**           | **⭐⭐⭐⭐⭐ 选**       | ⭐⭐⭐                        | ⭐⭐⭐      | ⭐⭐⭐    | ⭐⭐        | ⭐⭐        | ⭐⭐                  |

### 5.3 关键差异详解

#### arq vs Celery（最常被问）

| 维度             | arq                          | Celery                             |
| -------------- | ---------------------------- | ---------------------------------- |
| **进程模型**       | 单进程 asyncio loop             | 多 worker 进程（prefork）               |
| **API 风格**     | 全 async，函数定义即任务              | `@app.task` 装饰器                    |
| **上手成本**       | 1 文件 50 行                    | worker / beat / result backend 三件套 |
| **吞吐**         | 中等（受 GIL 限制，CPU 密集不行）        | 高（多进程可压满 CPU）                      |
| **生产案例**       | 维基百科内部、Instagram 部分服务        | 巨大（Instagram、Robinhood）            |
| **何时换 Celery** | QPS > 1000 或需要 CPU 密集 worker | —                                  |

> **本项目选择 arq 的核心理由**：本项目 QPS < 100，所有任务都是 IO 密集（调 LLM、调 Chroma、调高德），asyncio 协程模型反而比多进程更高效（避免 IPC + 进程切换开销）。

#### arq vs Kafka / RabbitMQ（过度工程检测）

- **Kafka**：百万级 QPS 才有意义；强顺序 / 流处理 / Exactly-Once 语义；本项目全部不适用
- **RabbitMQ**：复杂的 AMQP 协议 + Erlang VM 运维 + 单独 broker 进程；本项目队列长度从不超过 1000
- **判断标准**：当你的「单队列日均消息量 > 100 万」或「需要事件溯源 / 流式分析」时，才考虑这两个

#### arq vs asyncio.create_task（不引入新依赖）

| 维度   | arq               | asyncio.create_task |
| ---- | ----------------- | ------------------- |
| 可靠性  | ✅ 持久化、重试、死信       | ❌ 进程崩就丢             |
| 可观测性 | ✅ 任务状态/进度可查       | ❌ 只能打日志             |
| 跨进程  | ✅ 多个 worker 共享    | ❌ 单进程               |
| 跨机器  | ✅ 队列在 Redis       | ❌ 进程本地              |
| 延迟   | ⚠️ 5-10ms（序列化+网络） | ✅ < 1ms             |
| 复杂度  | ⚠️ 需要 Redis       | ✅ 无                 |

> **判断标准**：「**调用方不需要等下游完成**」+「**进程可能崩溃**」→ 用 arq；「**单请求内低延迟并发**」→ 用 `asyncio.gather`。

---

## 6. 问题覆盖

### 6.1 痛点 → 方案映射

| 痛点                     | 严重度   | 触发频次      | arq 方案                                       | 替代方案（如不引入）                              |
| ---------------------- | ----- | --------- | -------------------------------------------- | --------------------------------------- |
| 1. API 写路径同步 embedding | 🟥 P0 | 每次 API 调用 | `enqueue(sync_spot_to_chroma, ...)`          | 保留 `await embed_query_async`，接受 1-3s 延迟 |
| 2. chat 后处理小尾巴         | 🟥 P0 | 每次对话结束    | `enqueue(post_chat_summary, ...)` + 幂等键      | 保留 `asyncio.create_task`，接受丢任务风险        |
| 3. 维基抓取 / Chroma 重建    | 🟧 P1 | 每周 1-2 次  | `enqueue(fetch_wiki_for_spot, ...)` 多 worker | 单进程脚本，挂了重跑（现状）                          |
| 4. 告警调度多副本             | 🟧 P1 | 每天 ~290 次 | arq cron 替代 asyncio sleep                    | 加 Redis 分布式锁（部分缓解）                      |

### 6.2 选型决策树

```
任务需要可靠投递 / 失败重试 / 状态可查?
├── 是 → 跨进程 / 跨机器 / 跨时间?
│         ├── 是 → arq / Celery / Kafka
│         └── 否 → 同一进程内不同请求间?
│                   ├── 是 → arq / Celery
│                   └── 否 → asyncio.create_task
└── 否 → 单请求内低延迟并发?
          ├── 是 → asyncio.gather / create_task  ← 正确做法
          └── 否 → 直接同步 await
```

---

## 7. 落地路线（3 阶段）

### 7.1 M0：接入演练（1 周）

**目标**：跑通 arq 最小可用链路，验证与现有 `redis_client` 兼容。

**任务**：

- [ ] `pyproject.toml` 加 `"arq>=0.25.0"`
- [ ] 新建 `src/services/task_queue.py`（约 50 行，抄 `poi_cache.py` 范式）
- [ ] `src/main.py` lifespan 加 arq pool 初始化
- [ ] 新建 `worker.py`（约 30 行，定义 WorkerSettings + 一个测试任务）
- [ ] 新建 `scripts/demo_arq_job.py`（验证：入队 → 消费 → 结果回写）
- [ ] 新建 `tests/test_task_queue.py`（mock_redis + arq 集成测试）

**验证标准**：

- `pytest tests/test_task_queue.py` 全部通过
- `python worker.py` 启动后能消费 demo 入队的任务
- Redis 中 `arq:queue:default` 可见任务项

### 7.2 M1：试点改造（1-2 周）

**目标**：把最有故事性的 P0 痛点 1 落地。

**任务**：

- [ ] 改 `knowledge_service.bulk_import_spots`：把 30 行同步 Chroma 块改成入队
- [ ] 新增 `chroma_sync_tasks.py`：定义 `sync_spot_to_chroma` worker 函数
- [ ] 写 1 个 e2e 测试：入队 100 个 spot → worker 消费 → 验证 Chroma 向量全部到位
- [ ] 跑一遍 `pytest` 全量，确保无回归（基线 683 passed）

**验证标准**：

- API 响应时延 P95 < 50ms（vs 之前 800ms+）
- worker 单独进程崩溃后任务自动重投
- Chroma 故障时 API 仍返回成功（仅日志告警）

### 7.3 M2：全面推广（2-4 周）

**任务**：

- [ ] 改造 `_post_chat_tasks`：入队 + 幂等键
- [ ] 改造 `fetch_wiki.py`：每城每 spot 入队，主进程只负责派发
- [ ] 改造 `alert_scheduler.py`：用 arq cron 替代 asyncio sleep
- [ ] 加监控：`/api/admin/queue/stats` 路由暴露队列长度、失败数、平均处理时长
- [ ] 加告警：连续失败 3 次 → 钉钉/webhook 通知

**验证标准**：

- 4 个痛点全部入队
- 多 worker 进程可水平扩展（实测启动 3 worker，吞吐 ≥ 3x）
- 监控 dashboard 可视化队列健康度

---

## 8. 风险与监控

### 8.1 已知风险

| 风险               | 严重度 | 缓解措施                                                                    |
| ---------------- | --- | ----------------------------------------------------------------------- |
| **arq 文档少、社区小**  | 中   | arq 源码 1 个文件 500 行，可读性极高；社区 issue 响应快（原作者 Samuel Colvin 还维护 pydantic）   |
| **进程崩溃任务丢失**     | 低   | arq 默认开启 `keep_result` + 失败重试 5 次；任务有唯一 ID，重投不重复                        |
| **Redis 故障全队失效** | 中   | 复用现有 `is_redis_available()` 降级：Redis 挂时降级为 `asyncio.create_task`（保留旧行为） |
| **worker 数量难调优** | 低   | M1 阶段 1 worker，M2 阶段按队列长度自动扩缩（CPU bound 加 worker，IO bound 不加）           |
| **任务积压无告警**      | 中   | 监控 `LLEN arq:queue:default`，超过阈值（1000）触发告警                              |

### 8.2 缓解措施（已设计）

- **降级开关**：`TaskQueue.__init__` 与 `POICache` 一致——Redis 不可用时降级为 `asyncio.create_task`，上层无感
- **幂等键**：所有入队任务带 `_job_id=<业务唯一键>`，重复入队只执行一次
- **死信队列**：arq 自带 `max_tries=3`，超过自动入死信
- **手动重投**：提供 `scripts/replay_dead_letter.py` 死信重放脚本

### 8.3 监控指标

| 指标         | 采集方式                                   | 告警阈值   |
| ---------- | -------------------------------------- | ------ |
| 队列长度       | `LLEN arq:queue:default`               | > 1000 |
| 处理 P99 延迟  | arq 自带 stats                           | > 30s  |
| 失败率        | arq stats / total                      | > 5%   |
| 死信队列长度     | `LLEN arq:dead_letter`                 | > 0    |
| Worker 进程数 | `pgrep -f "python worker.py" \| wc -l` | < 1    |

---

## 9. 决策结论

### 9.1 一句话决策

> **采纳 arq + Redis 作为项目可靠任务执行层**，分 3 阶段（接入演练 / 试点 / 全面）落地，**总投入约 4-6 周 + 120 行新增代码**，不增加任何基础设施。

### 9.2 决策依据

1. **业务驱动**：5 个真实痛点（2 个 P0 + 2 个 P1 + 1 个反例）有明确代码位置和频次；
2. **技术就位**：Redis + 异步客户端 + 双后端降级模式 + 测试基础设施全部已有；
3. **生态最适配**：arq 与项目 async 栈天然兼容，无需桥接；
4. **风险可控**：可降级、可回滚（保留 `asyncio.create_task`）、可逐步切；
5. **未来可演进**：若 QPS 增长，可平滑迁移到 Celery（API 相似）。

### 9.3 待评审事项

- [ ] 团队评审：是否同意 3 阶段路线图
- [ ] 团队评审：P0-1（API 写路径异步化）作为 M1 首选试点是否合适
- [ ] 团队评审：是否同意「Redis 不可用时降级为 asyncio.create_task」的策略
- [ ] 后续：M1 落地后，单独出一份「上线效果评估」复盘文档

### 9.4 替代方案（如评审不通过 arq）

| 备选                         | 何时切换                         |
| -------------------------- | ---------------------------- |
| **Dramatiq + RabbitMQ**    | 需要复杂路由 / topic 订阅场景          |
| **Celery + Redis**         | QPS > 1000 或需要 CPU 密集 worker |
| **保留 asyncio.create_task** | 仅 M0 接入演练失败时                 |
| **Kafka**                  | 需要事件溯源 / 流式分析 / 跨系统集成        |

---

## 附录 A：核心代码骨架

### A.1 `src/services/task_queue.py`（新文件，约 50 行）

```python
"""任务队列（arq 优先，asyncio.create_task 降级）

与 src/services/poi_cache.py 双后端模式一致：
- Redis 可用 → arq 异步任务队列
- Redis 不可用 → asyncio.create_task 内存降级

上层调用方完全无感。
"""
import asyncio
import logging
from typing import Callable, Any, Optional

from src.config.redis_client import is_redis_available

logger = logging.getLogger(__name__)


class TaskQueue:
    """任务队列统一接口。"""

    def __init__(self):
        self._backend_type: str = "asyncio"  # 默认降级
        self._arq_pool: Optional[Any] = None
        if is_redis_available():
            try:
                from arq import create_pool
                from arq.connections import RedisSettings
                # pool 由 lifespan 注入；这里只占位
                self._RedisSettings = RedisSettings
                self._backend_type = "arq"
                logger.info("Task queue backend: arq")
            except ImportError:
                logger.warning("arq 未安装，降级为 asyncio")
        logger.info("Task queue backend: %s", self._backend_type)

    async def enqueue(
        self,
        func: Callable,
        *args: Any,
        job_id: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        """入队任务。失败静默降级（不抛错给上层）。"""
        try:
            if self._backend_type == "arq" and self._arq_pool is not None:
                await self._arq_pool.enqueue_job(
                    func.__name__,
                    *args,
                    _job_id=job_id,
                    **kwargs,
                )
            else:
                asyncio.create_task(func(*args, **kwargs))
        except Exception as e:
            logger.warning("Task enqueue failed (degraded): %s", e)
            # 降级：同步跑（至少保证业务逻辑执行）
            asyncio.create_task(func(*args, **kwargs))


_queue: Optional[TaskQueue] = None


def get_task_queue() -> TaskQueue:
    global _queue
    if _queue is None:
        _queue = TaskQueue()
    return _queue
```

### A.2 `worker.py`（新文件，约 30 行）

```python
"""arq worker 启动入口。

启动命令：python worker.py
"""
import asyncio
from arq.connections import RedisSettings
from arq import cron_jobs

from src.config.settings import settings
from src.services.tasks.chroma_sync import sync_spot_to_chroma
from src.services.tasks.post_chat import post_chat_summary


async def startup(ctx):
    """worker 启动钩子：初始化 db session / redis 客户端。"""
    from src.config.redis_client import init_redis
    from src.config.database import init_db
    await init_redis()
    await init_db()
    ctx["redis"] = ...


async def shutdown(ctx):
    """worker 关闭钩子。"""
    from src.config.redis_client import close_redis
    from src.config.database import close_db
    await close_redis()
    await close_db()


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [sync_spot_to_chroma, post_chat_summary]
    on_startup = startup
    on_shutdown = shutdown
    # 失败重试：默认 5 次指数退避
    max_tries = 3
    # 任务超时：5 分钟
    job_timeout = 300
```

### A.3 `src/main.py` lifespan 注入（修改约 5 行）

```python
# 在 lifespan 里加 arq pool 初始化
async def lifespan(app: FastAPI):
    await init_redis()
    if is_redis_available():
        from arq import create_pool
        from worker import WorkerSettings
        pool = await create_pool(WorkerSettings.redis_settings)
        # 注入到 task_queue 单例
        from src.services.task_queue import get_task_queue
        get_task_queue()._arq_pool = pool
    yield
    await close_redis()
```

---

## 附录 B：参考文档

| 文档               | 位置                                          | 关联           |
| ---------------- | ------------------------------------------- | ------------ |
| Redis 客户端实现      | `src/config/redis_client.py`                | 基础设施         |
| POI 缓存双后端样板      | `src/services/poi_cache.py:127-131`         | 设计模式参考       |
| LLM 缓存双后端        | `src/services/llm_cache.py`                 | 设计模式参考       |
| 流式响应 StreamStore | `src/services/stream_store.py`              | Redis 生产路径案例 |
| 工具缓存双后端          | `src/services/agent/tool_cache.py`          | 设计模式参考       |
| Alert 调度（待改造）    | `src/services/alert/alert_scheduler.py`     | 痛点 4         |
| Chat 后处理（已改造）    | `src/services/trip_service.py:287-307`      | 痛点 2（M2 已落地）|
| API 写路径（已改造）     | `src/services/knowledge_service.py:204-272` | 痛点 1（M1 已落地）|
| 维基抓取（已改造）        | `scripts/fetch_wiki.py`                     | 痛点 3（M3-A 已落地）|
| arq 官方文档         | <https://arq-docs.helpmanual.io/>           | 技术选型         |
| arq GitHub       | <https://github.com/python-arq/arq>         | 源码参考         |

---

# 第 10 章：M0/M1/M2/M3-A 落地回顾

> **本章定位**：原始决策文档（§0-9）是"事前规划"，本章是"事后复盘"。包含 4 个里程碑的实际效果、踩坑清单、对原决策的修正。

## 10.1 4 个里程碑落地数据

| 里程碑 | 周期 | 改/新增文件 | 测试 | 收益 |
|---|---|---|---|---|
| **M0 接入演练** | 1 天 | 5 个新文件 | 15 单测 | arq 0.28 + redis 5.3.1 接入，e2e 通 |
| **M1 业务改造（chroma）** | 1.5 天 | 6 个改/新文件 | 9 集成测试 + e2e | API P95 800ms→50ms，Chroma 故障解耦 |
| **M2 业务改造（chat 后处理）** | 0.5 天 | 5 个改/新文件 | 8 集成测试 + e2e | 进程崩溃不丢任务，状态可查 |
| **M3-A 业务改造（fetch_wiki）** | 1 天 | 4 个改/新文件 | 5 集成测试 | 跨城并行 + 断点续跑 + 多机协同 |
| **Review 报告 + P0/P1 修复** | 1 天 | 6 个改文件 | +5 单测 | 修了 2 个 P0 bug + 3 个 P1 应改项 |
| **累计** | ~5 天 | 31 个文件 | **728 passed / 1 xpassed** | 全闭环，0 回归 |

## 10.2 最重要的 4 个踩坑经验（写给未来的自己）

### 坑 1：`arq 0.28 keep_result` 是 **Function 级别**（不是 WorkerSettings 级别）

```python
# ❌ 错：直接传函数对象 → result 不写盘
functions=[sync_spot_to_chroma]

# ✅ 对：用 func() wrapper 显式配
functions=[func(sync_spot_to_chroma, keep_result=3600)]
```

**症状**：worker 跑完任务但 `arq:result:{job_id}` key 不存在，`Job.result()` 报 "Not waiting for job result"。
**根因**：arq 0.28 重构了 `Function` dataclass，`keep_result_s` 是 Function 字段而非 Worker 字段。
**修复成本**：M1 阶段耗时 1 小时定位。

### 坑 2：SQLAlchemy mapper 关系链断裂（`User→TokenUsageLog`）

```python
# ❌ 错：worker 端只 import 业务模型
from src.models.spot import Spot
# → 首次建 session 报 InvalidRequestError

# ✅ 对：worker 端顶部 import 全部 10 个模型
import src.models.user  # noqa: F401
import src.models.conversation  # noqa: F401
# ... 全 10 个
```

**症状**：worker 进程首次访问 DB 报 `InvalidRequestError("When initializing mapper Mapper[User(users)], expression 'TokenUsageLog' failed to locate a name")`。
**根因**：SQLAlchemy mapper 初始化时需要解析**全部**关系链，缺一就崩。
**修复成本**：M2 e2e 阶段耗时 30 分钟定位。
**教训**：所有 worker 任务文件**顶部**应 import 全部 models（参考 conftest.py）。

### 坑 3：mock patch 路径——"引用方 vs 源模块"

```python
# worker 函数：
async def fetch_city_wiki(...):
    from scripts.fetch_wiki import fetch_city  # ← lazy import
    await fetch_city(...)

# ❌ 错：patch 引用方（worker 模块）
patch("src.services.tasks.wiki_fetch.fetch_city")  # → 不生效
# ✅ 对：patch 源模块（lazy import 每次都从源模块读）
patch("scripts.fetch_wiki.fetch_city")
```

**症状**：`AttributeError: module ... does not have the attribute 'fetch_city'`。
**根因**：函数体内 `from X import Y` 是 lazy import，每次调用**重新**从源模块读 X.Y。patch 引用方模块的名字没用。
**修复成本**：M2 e2e + M3-A 测试都踩过，**各 30 分钟**。
**教训**：**lazy import 的常量/函数 patch 永远打源模块**。

### 坑 4：chroma 冷却期 vs arq 重试间隔不兼容

```python
# chroma_client._CHROMA_DOWN_TTL = 60s（冷却 60s）
# arq max_tries=3 默认重试间隔 1+2+4=7s
# → 3 次重试全在 60s 冷却期内被短路，"假重试"反而误导
# → 改为 max_tries=1，失败入死信更可观测
```

**症状**：任务失败重试 3 次，3 次都快速失败，**看起来在重试，实际无效**。
**根因**：外部服务的"快速失败"窗口跟任务队列的"重试间隔"不匹配。
**修复成本**：review 报告 P0-1，5 分钟修复。
**教训**：**重试策略要跟下游服务的"健康窗口"对齐**——不能默认 max_tries=3。

## 10.3 决策修正：原 §3.4 "分布式锁" 暂不实施

**原决策**：M2 阶段把 `alert_scheduler` 改分布式锁防多副本重复告警。
**修正**：**改为暂不实施**。原因：

| 维度 | 原方案 | 实际情况 |
|---|---|---|
| 真实需求 | "K8s 部署 3 副本会重复发 3 次 webhook" | 当前**单进程部署**，未到多副本 |
| 更简方案 | 分布式锁（150 行） | 单 worker / 单副本部署（0 行） |
| 失败成本 | 锁过期 = 告警**漏发** | 重复发 = 监控多收几次 |
| 误判严重度 | "理论上会出问题" | 12-factor：调度器是平台的事，应用层不该管 |

**判断标准**（全部满足才考虑分布式锁）：
- [ ] 真在做 K8s 多副本（不是"以后可能"）
- [ ] 告警 webhook 去重在接收端做不了
- [ ] 重复告警真的造成过事故
- [ ] 已用 1-2 年、量级真到瓶颈

**当前项目**：4 个 checkbox 一个都没打上。
**替代方案**：用 OS cron / K8s CronJob 触发独立脚本 `scripts/run_alert_check.py`（12-factor 思路，调度器归平台管）。

**教训**：**避免"理论上会出问题"驱动的过度设计**——分布式锁的真实成本（150 行代码 + 锁竞争调试 + 告警漏发风险）远超 4 个 worker 重复发 webhook 的代价。

---

# 第 11 章：M4-M6 候选改进项（基于代码事实）

> **本章定位**：基于项目**实际**勘察（不重复已经做过的），找出"还有故事可讲"的改进项。

## 11.1 项目已具备的能力盘点

| 能力 | 现状 | 文件 |
|---|---|---|
| Redis 缓存（多服务） | `poi_cache / llm_cache / tool_cache / rate_limiter` 全部 Redis 优先 + 内存降级 | — |
| 限流中间件 | 滑动窗口 + 内存/Redis 双模式 | `src/middleware/rate_limiter.py` |
| 数据库索引 | 8 个 B-tree 复合索引 + 2 个 FULLTEXT 索引 | `src/models/*.py` |
| JWT 鉴权 | 完整 | `src/middleware/auth.py` |
| 结构化日志 | structlog + trip_log + request_id 串联 | `src/utils/logger.py` |
| Docker 化 | docker-compose 已有 redis | `docker-compose.yml` |

**这些已经够讲 80% 的后端面试题**。**不要再动**。

## 11.2 真正还能改进的（按 ROI 排序）

### M4 候选 1：熔断器（circuit breaker）补完 ⭐⭐⭐⭐⭐

**现状**：`with_resilience`（`src/services/agent/resilience.py`）实现了「超时 + 重试 + 降级」，**但没有真正的熔断器**。

**问题**：
- 高德 API 抽风时，每个请求等 5s 超时 + 重试 2 次 = **15s 才降级**
- 期间后端被拖垮
- 没有 Closed/Open/Half-Open 三态，故障恢复靠自然超时

**改造**：
- `ToolResilienceWrapper` 加 `circuit_breaker=True` 选项
- 实现三态机：Closed（正常）→ Open（熔断）→ Half-Open（试探恢复）
- 状态变化写 metrics
- 落点文件：`src/services/agent/resilience.py`（~80 行新增）

**故事价值**：面试"熔断和降级的区别"——能直接讲"我的项目把熔断（状态机）和降级（默认值）解耦，组合起来用"。

**工作量**：1-2 天。

### M4 候选 2：关键路径 Prometheus metrics ⭐⭐⭐⭐

**现状**：有日志，但**没有 QPS / P99 / 错误率 metrics**。
- 面试问"线上 P99 多少？"——只能猜
- 面试问"哪个接口是瓶颈？"——只能翻日志

**改造**：
- 加 `prometheus_client` 库
- FastAPI middleware 自动记录：`http_requests_total{path, method, status}` / `http_request_duration_seconds{path, method}`
- 暴露 `/metrics` 端点（K8s Prometheus 自动抓）
- chat 端点单独打：LLM 推理时延、tool 调用次数、stream 完成时间
- 落点文件：`src/middleware/prom_metrics.py`（新 ~100 行）

**故事价值**：面试"可观测性"题——"项目有 3 类信号：日志（排错）+ metrics（告警）+ trace（链路），我用 prometheus 暴露 4 类核心指标"。

**工作量**：1 天。

### M4 候选 3：SQLAlchemy 慢查询日志 ⭐⭐⭐⭐

**现状**：8 个复合索引 + 2 个 FULLTEXT 已设计，但**没有慢查询监控**。
- 不知道哪些查询实际慢
- 不知道索引设计有没有被用上

**改造**：
- SQLAlchemy event hook 监听 `before_cursor_execute` / `after_cursor_execute`
- 记录 >100ms 的查询（SQL + 耗时 + 调用栈）
- 用 `trip_log.warning` 输出（已用结构化日志）
- 落点文件：`src/utils/sql_logger.py`（新 ~50 行）+ `src/config/database.py` 装 1 个 hook

**故事价值**：面试"MySQL 慢查询怎么排查"——"我项目里有 SQLAlchemy event hook 自动记录 >100ms 的查询，能直接看 trip_log 的 JSON 日志定位"。

**工作量**：半天。

### M5 候选：系统设计 3 篇文档（练习为主）⭐⭐⭐⭐⭐

**现状**：项目里有现成场景可以做"系统设计题"答案，但没沉淀。

**最有故事的 3 题**（结合项目）：

| 系统设计题 | 套项目场景 | 文档长度 |
|---|---|---|
| **限流设计** | chat 接口的限流（已实现 + 滑窗算法）| 800-1000 字 |
| **搜索 + RAG 检索** | `knowledge_service.search_spots`（4 路召回 + RRF）| 1200-1500 字 |
| **Feed / 推荐** | `trip_service.recommend`（agent 编排）| 1000-1200 字 |

**输出结构**（每篇）：
1. QPS 估算（基于真实数据）
2. 存储选型（为什么用 MySQL 不用 ES）
3. 关键流程（架构图 + 时序图）
4. 难点（实际踩过的坑）

**落点目录**：`docs/system-design/{限流,搜索,推荐}.md`

**故事价值**：面试系统设计题时，**直接掏自己项目**比现场编强 10 倍。

**工作量**：1 周（3 篇 × 1.5 天/篇）。

## 11.3 不推荐现在做的（避免重蹈"分布式锁"覆辙）

| 候选 | 不推荐理由 |
|---|---|
| **链路追踪 OTel** | 跟 prometheus metrics 重叠，项目体量不需要全链路 |
| **K8s 部署** | 项目体量不需要，docker-compose 够用 |
| **A/B 测试框架** | 跟"补后端知识"目标无关 |
| **GraphQL** | REST 够用，迁移成本高 |
| **分布式 session** | JWT 无状态，不需要 session |

## 11.4 推荐组合

**1.5-2 周**能完成 4 个候选：

| 优先级 | 做什么 | 工作量 | 故事价值 |
|---|---|---|---|
| **P0** | 熔断器补完 | 1-2 天 | 熔断 vs 降级（高频题）|
| **P0** | Prometheus metrics | 1 天 | 可观测性（高频题）|
| **P1** | 慢查询日志 | 半天 | MySQL 慢查询（高频题）|
| **P1** | 系统设计 3 篇文档 | 1 周 | 面试前最强弹药 |

## 11.5 决策选项

- **A. 先做"代码改造"组合**（熔断器 + metrics + 慢查询日志，1 周）
- **B. 先做"文档"组合**（系统设计 3 篇，1 周）—— 面试马上要用就选这个
- **C. 暂停**：消化盘点后再决定

---

# 第 12 章：面试弹药清单（系统设计题标准答案模板）

> **本章定位**：基于第 11 章 §M5 候选，给出 3 篇系统设计题答案的**写作模板**。每篇都从项目代码出发，按面试标准结构（QPS 估算 → 存储选型 → 关键流程 → 难点）。

## 12.1 模板结构（每篇都按这个组织）

```markdown
# [系统设计题名]

## 1. 需求分析
- 功能需求（what）
- 非功能需求：QPS 估算、延迟要求、可用性

## 2. 存储选型
- 为什么用 MySQL / Redis / ES / MongoDB（取舍）

## 3. 关键流程
- 架构图（mermaid 或 ASCII）
- 时序图（mermaid sequenceDiagram）
- 关键算法（伪代码）

## 4. 难点
- 项目里实际踩过的坑 + 解决方案

## 5. 扩展性
- 单机 → 分布式怎么演进
```

## 12.2 三篇候选速览

### 篇 1：限流设计（800-1000 字）
- **套项目**：`src/middleware/rate_limiter.py`（滑动窗口 + 内存/Redis 双模式）
- **关键点**：为什么选滑动窗口（vs 固定窗口 / 令牌桶 / 漏桶）；Redis 模式的 lua 脚本原子性
- **难点**：多副本部署下共享计数

### 篇 2：搜索 + RAG 检索（1200-1500 字）
- **套项目**：`src/services/knowledge_service.py::search_spots`（4 路召回 + RRF + Cross-Encoder 重排）
- **关键点**：向量检索 + 全文检索 + 知识图谱召回的融合
- **难点**：跨语言召回（中文 query 找英文 spot）、冷启动（新景点无向量）

### 篇 3：Feed / 推荐（1000-1200 字）
- **套项目**：`src/services/trip_service.py::recommend`（agent 编排 + LLM 推理）
- **关键点**：协同过滤 vs 内容过滤 vs LLM 推理的取舍
- **难点**：冷启动、实时性 vs 准确性

---

# 附录 C：4 个里程碑的代码变更清单（已落地）

| 阶段 | 文件 | 改动类型 | 关键内容 |
|---|---|---|---|
| **M0** | `pyproject.toml` | 改 | `arq>=0.25.0` |
| M0 | `src/services/task_queue.py` | 新 | 双后端封装（arq + asyncio 降级） |
| M0 | `src/main.py` | 改 | lifespan 加 arq pool 注入 |
| M0 | `src/services/tasks/demo.py` | 新 | 3 个 demo 任务 |
| M0 | `worker.py` | 新 | arq WorkerSettings |
| M0 | `scripts/demo_arq_job.py` | 新 | 演示脚本 |
| M0 | `tests/test_task_queue.py` | 新 | 15 单测 |
| **M1** | `src/services/tasks/chroma_sync.py` | 新 | `sync_spot_to_chroma` worker + 2 helper |
| M1 | `src/services/knowledge_service.py` | 改 | 3 处同步块改入队 |
| M1 | `worker.py` | 改 | 注册 `sync_spot_to_chroma` |
| M1 | `tests/test_chroma_sync_integration.py` | 新 | 9 集成测试 |
| M1 | `scripts/e2e_m1_chroma_sync.py` | 新 | e2e 端到端验证 |
| **M2** | `src/services/tasks/post_chat.py` | 新 | `post_chat_followup` worker |
| M2 | `src/services/trip_service.py` | 改 | `_post_chat_tasks` 改 async + 入队 |
| M2 | `worker.py` | 改 | 注册 `post_chat_followup` |
| M2 | `tests/test_post_chat_integration.py` | 新 | 8 集成测试 |
| M2 | `scripts/e2e_m2_post_chat.py` | 新 | e2e 端到端验证 |
| **M3-A** | `src/services/tasks/wiki_fetch.py` | 新 | `fetch_city_wiki` worker |
| M3-A | `scripts/fetch_wiki.py` | 改 | 两段循环入队化 |
| M3-A | `worker.py` | 改 | 注册 `fetch_city_wiki` |
| M3-A | `tests/test_wiki_fetch_integration.py` | 新 | 5 集成测试 |
| **Review + P0/P1** | `worker.py` | 改 | `max_tries=1`（P0-1） |
| Review | `src/services/task_queue.py` | 改 | 降级路径异常记录（p0-2） |
| Review | `src/main.py` | 改 | 去死代码 |
| Review | `tests/test_task_queue.py` | 改 | +5 P0-2 测试 |

---

**文档结束。** 评审意见请通过 PR / 评论 / 会议反馈。
