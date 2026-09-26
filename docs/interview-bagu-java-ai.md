# 项目技术栈基础八股（Java 版后端 + AI 应用层）

> 生成于 2026-09-21。每节格式：**Q 问法 → A 标准答案要点 → 锚点（本项目怎么答）**。
> 优先级：**P0** 必问且答不上直接挂；**P1** 大概率问；**P2** 深追或看岗位才问。

---

## 0. 先记住一句话主线（决定面试官往哪挖）

简历写了什么，八股就问什么。这份稿子的覆盖顺序按真实追问概率排：
**虚拟线程与并发 → Spring/JPA 与连接池 → PostgreSQL 索引与事务 → Redis → SSE/HTTP → 限流熔断幂等 → 向量检索与 RAG → Agent 与评测**。

---

## 1. Java 21 / JVM 【P0】

**Q：虚拟线程是什么？和平台线程、协程的区别？**
A：虚拟线程是 JEP 444（Java 21 正式）提供的由 JVM 调度的轻量线程，一个虚拟线程对应一个 `Continuation`，阻塞时把栈帧卸载（unmount）回堆，让出 carrier thread（底层是 `ForkJoinPool`）。平台线程是 OS 线程 1:1 映射，创建要 1MB 级栈且受内核调度限制，几千个就到顶了。它属于 M:N 调度的用户态线程，和 Go 协程思路一致。

锚点：`BgeEmbedder` / `BgeReranker` 模型预热、`WorkerScheduler` 队列消费、`DegradedTaskRunner` 内存降级执行都用了虚拟线程——理由都是"IO 阻塞 + 数量不可预测"。

**Q：虚拟线程什么时候不该用？**
A：三种情况。（1）CPU 密集：没有阻塞点，卸载无意义，还多了调度开销；（2）`synchronized` 块内阻塞会 **pinning**——虚拟线程被钉在 carrier 上不能卸载，退化成平台线程行为（JDK 21 如此，后续版本在改善），临界区应改用 `ReentrantLock`；（3）大量 `ThreadLocal`：几十万虚拟线程会让每个 ThreadLocal 都有一份副本，内存放大，且不能用 ThreadLocal 做池化资源共享。

锚点：本项目的请求上下文用 MDC（`RequestIdFilter`），要能说清"虚拟线程下 MDC 不会自动跨线程传递，必须在任务提交处手动复制"。

**Q：还要不要线程池？**
A：不需要池化虚拟线程，创建成本极低，用完即弃（`Executors.newVirtualThreadPerTaskExecutor()`）。但**下游资源仍需限流**：DB 连接池、上游 LLM QPS 是固定的，虚拟线程把并发放大到十万就会打爆它们，所以要显式 `Semaphore` 或令牌桶。

锚点：并发守卫（`agent/semaphore.py` 语义，Java 侧 `middleware/` 并发守卫，超限返回 429）正是这个作用——这是"我知道虚拟线程的坑"的最好证据。

**Q：G1 和 ZGC 怎么选？Full GC 怎么排查？**
A：G1 把堆分 Region、维护 Remembered Set、以 `-XX:MaxGCPauseMillis` 为目标做增量标记 + Mixed GC，适合大部分后端服务（默认）。ZGC 用着色指针 + 读屏障，暂停与堆大小基本无关（亚毫秒），适合大堆低延迟。Full GC 常见原因：堆内存不足或元空间、`System.gc()`、晋升失败（to-space exhausted）、ExplicitGC 策略。排查：`-Xlog:gc*`、`jstat -gcutil`、`jmap -histo`、堆 dump 用 MAT 看支配树。

锚点：别说"我调过 GC"，除非你真的测过。可以说：本地 16GB 机器跑 ONNX 推理 + 模型常驻，堆配置主要是给模型留余量，没做线上级调优。

**Q：`volatile`、`synchronized`、`ReentrantLock`、原子类的边界？**
A：JMM 下 `volatile` 只保证可见性和禁止重排，不保证原子（`i++` 仍不安全）；`synchronized` 具备互斥 + 可见性，且锁升级路径是无锁→偏向→轻量→重量；`ReentrantLock` 额外支持可中断、超时、公平、多 Condition。单字段 CAS 用 `Atomic*`，多字段一致性仍需锁或不可变对象。

锚点：熔断器的三态切换、`_load_failed` 这类降级闸门开关，都是"状态读多写少 + 需要可见性"，可以讲你怎么选的（`AtomicReference` / `volatile` 状态字段）。

**Q：`HashMap` 原理、扩容、为什么线程不安全？**
A：数组 + 链表 + 红黑树，树化阈值 8、退化 6，负载因子 0.75，容量 2 的幂，扰动函数高 16 位异或低 16 位。扩容 2 倍并重排（JDK8 只移动原位置或原位置+oldCap）。并发下会丢更新，JDK7 头插法成环，所以要么 `ConcurrentHashMap`（CAS + 分段 `synchronized`，size 用 `baseCount`+`CounterCell`），要么 `Collections.synchronizedMap`。

锚点：双后端缓存的内存后端就是进程内 `Map`（有容量上限 128 的 `StreamStore` 内存降级），要能说清"进程内缓存在多实例下不共享，所以只作降级不作主存储"。

**P2：类加载器与双亲委派、`CompletableFuture` 的异常与组合、`record`/`sealed`/`pattern matching` 用法、`Stream` 与并行流的坑（共享 ForkJoinPool）、`String` 常量池、`equals/hashCode` 契约、软/弱引用、`ThreadLocal` 内存泄漏（Entry 的 key 是弱引用、value 强引用需手动 remove）。**

---

## 2. Spring Boot 3.3 / Spring 核心 【P0】

**Q：Bean 的生命周期？**
A：实例化（构造器/工厂方法）→ 属性填充 → `Aware` 回调（`BeanNameAware`/`ApplicationContextAware`）→ `BeanPostProcessor.postProcessBefore` → `@PostConstruct` → `InitializingBean.afterPropertiesSet` → init-method → `postProcessAfter`（AOP 代理在这一步生成）→ 使用 → `@PreDestroy`/destroy-method。

**Q：循环依赖怎么解？为什么需要三级缓存？**
A：`singletonObjects`（成品）→ `earlySingletonObjects`（提前暴露的半成品，可能是代理）→ `singletonFactories`（`ObjectFactory`，用来按需生成早期引用，把"AOP 代理的创建时机"推迟到确实发生循环依赖时）。构造器注入、`@Async`（代理在 postProcessAfter，太晚）都无法解决，只能 `@Lazy` 或改设计。原型作用域不支持。

锚点：真实风险点——`ChatAgent` 依赖工具集合、工具又依赖 `ChatAgent` 的场景，用 `ObjectProvider` 延迟取。

**Q：自动装配原理？Boot 3 有什么变化？**
A：`@SpringBootApplication` = `@SpringBootConfiguration` + `@EnableAutoConfiguration` + `@ComponentScan`；`AutoConfigurationImportSelector` 读取 `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`（Boot 2 是 `spring.factories`），再靠 `@ConditionalOnClass/OnProperty/OnMissingBean` 筛掉不适用的配置。写 starter：`AutoConfiguration` + `ConfigurationProperties` + imports 文件 + `@ConditionalOnMissingBean` 让用户可覆盖。

**Q：`@Transactional` 什么时候失效？**
A：八个高频场景：同类内部自调用（不走代理）、方法非 `public`、异常被 catch 吞掉、抛的是 checked 异常（默认只回滚 `RuntimeException`/`Error`，需 `rollbackFor`）、传播行为设错（`NOT_SUPPORTED`/`REQUIRES_NEW` 理解偏差）、方法 `static`、多数据源没指定 `transactionManager`、代理被 `final`/无参构造破坏。

**Q：传播行为？**
A：`REQUIRED`（默认，加入或新建）、`REQUIRES_NEW`（挂起外层，独立事务）、`NESTED`（保存点，外层回滚全回滚，内层回滚不影响外层）、`SUPPORTS`/`NOT_SUPPORTED`/`ALWAYS`/`MANDATORY`/`NEVER`。

锚点：本项目的"写 trip + 写 conversation + 入队异步 embedding 任务"要能讲清事务边界——**异步任务必须在外层事务提交后才入队**，否则 worker 读不到数据（用 `TransactionSynchronization.afterCommit` 或先提交再投递）。

**Q：JDK 动态代理和 CGLIB 的区别？**
A：JDK 基于接口，生成实现同一接口的 `$Proxy`，只能代理接口方法，走 `InvocationHandler`；CGLIB 生成目标类子类覆盖方法，不能代理 `final` 类/方法，需要无参构造可被绕过（Objenesis）。Boot 2.x 起 `proxyTargetClass=true` 默认 CGLIB。

**Q：Filter 和 Interceptor 的区别？WebMVC 的线程模型？**
A：Filter 是 Servlet 规范、拿到的是原始 request/response、在容器层生效、能改 body 要靠包装；Interceptor 是 Spring MVC 层、在 handler 前后、能拿到 `HandlerMethod` 和 ModelAndView。`DispatcherServlet` 默认一个请求占一个 Tomcat 工作线程（默认 max 200），要非阻塞得用 `WebFlux` 或 `Callable`/`DeferredResult`/异步 Servlet + 虚拟线程。

锚点：本项目 5 个 Filter（request-id、鉴权、限流、幂等、Prometheus）——要能说清顺序（`FilterOrderConfig`）以及为什么幂等 Filter **必须**跳过 SSE 路径（缓冲 body 会把流截断）。

**Q：内嵌 Tomcat 调优项？**
A：`server.tomcat.threads.max`、`accept-count`、`max-connections`、`connection-timeout`、`max-http-form-post-size`、`keep-alive-timeout`；长连接/SSE 会长期占用工作线程，因此流式接口对线程池压力最大。

**P2：`@Configuration` 的 proxyBeanMethods、`BeanFactoryPostProcessor` vs `BeanPostProcessor`、`ApplicationRunner` vs `CommandLineRunner`、Actuator 端点安全、`WebMvcConfigurer` vs 自动装配冲突排查、`spring.main.allow-circular-references` 默认关闭（Boot 2.6+）。**

---

## 3. JPA / Hibernate + 连接池 【P1】

**Q：一级缓存、二级缓存，和 Spring 的"三级缓存"是一回事吗？**
A：不是。Hibernate 一级缓存是 `PersistenceContext`（一个事务/请求内，同一实体不重复查），二级缓存是 `EntityManagerFactory` 级别（需 provider，按实体配置 `@Cacheable`，注意集群失效）。Spring 三级缓存说的是单例 Bean 循环依赖，两个"三级"完全无关——这题就是考你会不会混。

**Q：N+1 怎么产生、怎么解？**
A：查 100 个父实体后，访问懒加载集合时逐条 SELECT。解法：`JOIN FETCH`（注意配合分页会内存分页，结果集膨胀）、`@EntityGraph`、`@BatchSize` / `hibernate.default_batch_fetch_size`（把 N 次变 log 次，`WHERE id IN (...)`）、DTO 投影（`select new`，根本不走实体）、`@EntityGraph` + `distinct`。

锚点：行程查询要返回 trip → days → spots 三层，讲清你用 DTO 投影 + batch fetch，而不是无限 join fetch。

**Q：为什么本项目向量字段标 `@Transient`？JPA 和 JdbcTemplate 怎么分工？**
A：pgvector 的 `vector` 类型 Hibernate 不认，`embedding <=> CAST(:vec AS vector)` 这类距离算子和 HNSW 索引提示必须走原生 SQL，实体里映射它会污染脏检查（Hibernate 会试图写回）。所以标量 CRUD、分页、关系用 JPA Repository，向量检索与全文检索用 `JdbcTemplate` 手写 SQL——**同一套 schema，两种访问方式各取所长**。

**Q：Hibernate 脏检查、乐观锁？**
A：快照比对，字段没改也 UPDATE 全部（可用 `@DynamicUpdate`）。并发更新用 `@Version`，冲突抛 `OptimisticLockException`，上层要决定重试还是返回 409。

**Q：HikariCP 连接池多大？**
A：`maximum-pool-size` 不是越大越好，经验起点 `核数 × 2 + 有效磁盘数`，瓶颈通常在 DB 端。连接泄漏用 `leak-detection-threshold`。虚拟线程让并发暴涨，**连接池会立刻变成新瓶颈**，必须配合信号量或队列上限。

**P2：`save()` 与 `saveAndFlush()`、`@Modifying` 与一级缓存清理、Specification/Criteria 与动态查询、投影接口 vs DTO、`ddl-auto` 各档位与生产为什么用 `none`（本项目坚持 `none`，表结构以 Python 版为准）、Flyway/Liquibase 迁移策略。**

---

## 4. PostgreSQL 16 + pgvector 【P0，Java 岗也会问】

**Q：MVCC 与隔离级别？**
A：Postgres 每行有 `xmin/xmax`，读不加锁、写只锁同行。RC（默认）每条语句取新快照，避免脏读；RR 事务开始取快照，同一事务内可重复读，**Postgres 的 RR 已经能避免大部分幻读**（靠快照），但 `SELECT FOR UPDATE`/写冲突场景仍可能触发序列化异常；真正的串行化用 `SERIALIZABLE`（SSI，靠读写危险结构检测 + 重试）。还有 Read Uncommitted（等同 RC）。（JDBC 里 `RR` 常见默认与 JPA 的交互要能说清。）

**Q：索引类型怎么选？**
A：B-tree（默认，等值 + 范围 + 排序 + 前缀 like 'abc%'）、Hash（仅等值）、GIN（全文 tsvector、jsonb、数组，"包含"类查询）、GiST（几何、范围、最近邻）、BRIN（时序大表，按 block 范围摘要，极小体积）、表达式/部分索引（`WHERE deleted=false`）、覆盖索引（`INCLUDE` 避免回表）。

**Q：怎么定位慢查询？**
A：`log_min_duration_statement` + `auto_explain`，然后 `EXPLAIN (ANALYZE, BUFFERS)`。看：估算行数与实际行数是否差一个数量级（→ 统计信息过期，跑 `ANALYZE`）、扫描类型（Seq Scan 是否该走 Index/Bitmap）、`Nested Loop` 的 inner 端是否被放大（→ 换 Hash Join 或加索引）、外部排序 `Sort Method: external merge`（→ `work_mem`）、`Buffers: shared read` 多（→ 缓存不足）、并行度。

**Q：HNSW 和 IVFFlat 的区别？参数怎么调？**
A：IVFFlat 先聚类再探测 `probes` 个簇，**必须在有数据后建/重建才能训练出好的质心**，召回随数据漂移下降。HNSW 是多层可导航小世界图：上层稀疏做粗定位、底层稠密做精搜，插入时贪心找邻居。参数：`m`（每节点邻居数，越大图越稠密、召回高但内存和建索引变慢）、`ef_construction`（建索引时候选队列长度）、查询期 `SET hnsw.ef_search`（默认 40，越大召回越高、延迟越高）。经验：HNSW 召回/延迟普遍优于 IVFFlat，代价是建索引更慢、内存更高。

锚点：`spots.embedding` 与 `spot_docs.embedding` 上都有 HNSW 索引（模型里 `postgresql_using="hnsw"`）。你要能说"我的向量是 512 维 bge-small，3 万条量级，HNSW 单机完全够，不需要 Milvus"。

**Q：pgvector 的距离算子？为什么用 cosine？**
A：`<->` L2、`<#>` 负内积、`<=>` 余弦距离。文本 embedding 通常归一化后用余弦（等价于内积），对向量长度不敏感。索引要与算子匹配——建索引时指定的 `distance_metric` 必须和查询算子一致，否则不走索引。

**Q：中文全文检索怎么做？**
A：`tsvector` + `tsquery`，内置 `to_tsvector(' chinese ' )` 分不了中文，需要 **zhparser**（scws 词库）或 `pg_jieba` 扩展做词元化，配合 GIN 索引（`to_tsvector` 上建 expression GIN），查询用 `plainto_/websearch_to_tsquery` + `ts_rank_cd` 排序，`websearch_to_tsquery` 对用户输入最友好（不会因语法错报 500）。弱匹配可加 `pg_trgm`。

**Q：为什么用 Postgres 一个库搞定，而不是 MySQL + 专用向量库？**
A：POC/中小规模下，一体化省掉双写与一致性同步（向量与标量同事务）、可以"向量相似 + `WHERE city=? AND rating>4`"混合过滤（标量谓词下推到索引扫描）、备份运维只一套、SQL 复用。数据到千万级、需要稀疏向量/多向量/复杂过滤 + 高 QPS 时应迁 Milvus/Qdrant/pgvectorscale，届时用异步任务回填双写。

**Q：Vacuum 和表膨胀？**
A：UPDATE/DELETE 留死元组，靠 autovacuum 回收（`n_dead_tup`、`autovacuum_vacuum_scale_factor`），大表要调小 factor 或加 naptime；长事务会 hold住 `xmin` horizon 导致回收不掉；`VACUUM FULL` 锁表（用 `pg_repack`）。索引膨胀同样看 `pg_stat_user_indexes`。

**P2：`SELECT COUNT(*)` 优化（分区/物化视图/估算）、分区表（range/list，剪枝）、`pg_stat_statements`、WAL 与 checkpoint、复制与主从延迟对读库的影响、`SELECT FOR UPDATE SKIP LOCKED`（用它做任务队列是常见替代 Redis 的方案）、JSONB 与 GIN、连接池 pgbouncer（transaction pooling 与 prepared statement 的冲突）、`ctid`、死锁排查 `pg_locks`。**

---

## 5. Redis 7 【P0】

**Q：为什么单线程还这么快？6.0 的多线程是什么？**
A：纯内存 + 单线程避开锁竞争和上下文切换 + epoll 事件循环；6.0 的 IO 多线程只并发改写/读取 socket 缓冲区，**命令执行仍是单线程**，所以 CPU 密集的 O(N) 命令（`KEYS`、`SMEMBERS` 大集合）依然会阻塞全部请求——这是线上事故常见来源。

锚点：你的 `arq:queue` 用 `LPUSH`/`BRPOP`，要能主动说"绝不在 Redis 上跑 `KEYS`，用 `SCAN` 游标"。

**Q：数据结构与底层编码？**
A：String(SDS)、List(listpack → quicklist → 7.x 后改为 listpack 容器)、Hash(listpack → hashtable)、Set(intset/listpack → hashtable)、ZSet(listpack → skiplist+hashtable)、Stream(rax 树)、HyperLogLog、Bitmap/Bitfield、Geo、Module（向量、Bloom）。

**Q：过期删除和内存淘汰？**
A：过期 = 惰性删除 + 定期任务抽样删除；内存到 `maxmemory` 按策略淘汰：`noeviction`（写报错）、`allkeys-lru`、`allkeys-lfu`、`volatile-*`（只在有 TTL 的 key 上生效）、`allkeys-random`。Redis 的 LRU/LFU 是**近似**算法（抽样 N 个），`lfu` 用衰减计数器，适合热点访问。

**Q：缓存穿透 / 击穿 / 雪崩？（必问，必须结合自己代码答）**
A：穿透（查不存在的 key）→ 空值缓存 + 短 TTL、布隆过滤器、入口校验；击穿（热 key 过期瞬间打穿）→ 互斥重建（只放一个请求回源）或逻辑过期（异步刷新）；雪崩（大批同时过期 / Redis 挂）→ TTL 加随机抖动、多级缓存、限流降级兜底。

锚点：这是你项目能拉开差距的地方——`DualBackendCache`（Redis + 进程内双后端）+ `poi_cache`（热点城市 1h TTL）+ `llm_cache`（SHA-256 prompt 哈希做 key）+ `tool_cache`（把 query 做 embedding 归一化后按余弦相似 ≥0.85 命中，属于**语义缓存**）。主动说"语义缓存的代价是每次要先算一次 embedding，所以我按工具维度只对高耗时工具开"。

**Q：分布式锁？**
A：`SET key uuid NX PX 30000` + 释放时用 Lua 比对 value 再删（防止删了别人的锁）；租约到期而业务未完成要"看门狗"续期（Redisson）；单实例锁不保证主从切换丢锁，Redlock 依赖多独立实例 + 时钟假设有争议（Martin Kleppmann 的批评值得读）。**结论级表述**：Redis 锁适合"减少重复工作"，不适合"必须互斥的正确性"，后者要靠 DB 唯一约束或带条件写的乐观锁。

锚点：`TaskQueue` 的 `SETNX` 是**幂等去重**而不是互斥锁，这个区分要讲清楚（配合 Redis 里存结果 `SETEX arq:result:{jobId} 3600`，重试直接拿缓存结果）。

**Q：Redis 做队列够吗？和 MQ 的差别？**
A：`LPUSH`+`BRPOP` 是"至少一次"，但消费者拿到就出队，进程崩了消息就丢，没有 ACK、没有重投、没有死信、没有消费者组。要么用 `BZPOPMIN` + 处理中集合 + 超时重投自己实现，要么直接上 `Stream`（`XADD`/`XREADGROUP`/`XPENDING`/`XACK`，天然有 PEL 与重投）。生产级我建议 Kafka/RabbitMQ，本项目是"单机个人项目 + 内存降级"这个取舍。

**Q：Redis 持久化和高可用？**
A：RDB（fork COW，快照，恢复快，可能丢几分钟）、AOF（`appendfsync everysec` 平衡点，`auto-aof-rewrite-percentage`，7.x 混合持久化默认开）、主从 + Sentinel（自动故障转移，异步复制仍会丢）或 Cluster（16384 slot，客户端重定向 MOVED/ASK，多 key 操作需同 hash tag `{}`）。

**P2：大 key/热 key 治理（拆分、本地缓存、读写分离、`--bigkeys`/`--hotkeys`）、pipeline vs Lua、`SCAN` 的游标语义（不保证不漏不保证不重）、Redis 与 DB 双写一致性（先更新 DB 再删缓存 + 延迟双删 / binlog 订阅）、内存碎片率 `mem_fragmentation_ratio`、`CLIENT LIST` 连接打满排查。**

---

## 6. 网络协议 / SSE / 流式 【P0，简历核心亮点必被追问】

**Q：SSE、WebSocket、长轮询怎么选？**
A：SSE = HTTP 上的 `text/event-stream`，服务端单向推、纯文本、自动重连（浏览器 `EventSource` 带 `Last-Event-ID`）、走普通 HTTP 栈和鉴权、支持 chunked；WebSocket 需 101 升级、全双工、二进制，但要自己管心跳与重连，且中间代理支持不总稳定；长轮询兼容性最好但开销最大。**LLM token 流是典型单向推送 → SSE 是最省事的选择。**

锚点：本项目前端不是用 `EventSource` 而是 `fetch` + ReadableStream 自己解析（因为要用 POST 传对话上下文并带 Authorization 头，`EventSource` 不支持 POST/自定义头），所以重连、退避、`Last-Event-ID` 全得自己实现（`src/api/request.ts` 的 `fetchStream`、`stream-parser.ts`）——**这一句能把"你和别人背一样的 SSE 答案"区分开。**

**Q：SSE 帧格式？`id:` 有什么用？**
A：`data:` 可多行（拼接后以 `\n` 分隔触发一次事件）、`event:` 事件名（`addEventListener` 分派）、`id:` 会被浏览器记为 lastEventId 并在重连时放进 `Last-Event-ID` 头、`retry:` 重连间隔、`:` 开头是注释（本项目用 `heartbeat` 注释帧防中间层空闲断连）。响应用 `Cache-Control: no-cache`、`Connection: keep-alive`、`Content-Type: text/event-stream; charset=utf-8`。

追问：你的事件类型放在 `data.type` 而不是 `event:` 字段，为什么？——答：前端只有一个解析入口、事件要支持自定义 JSON 负载与续传时的 seq 对齐，统一放 data 更容易做去重与类型收敛（TS 联合类型）。

**Q：断点续传怎么设计？（这是你最该讲透的一道）**
A：要素五个。（1）事件先写日志再下发：`XADD`/Redis List + `INCR seq`，TTL 兜底（本项目 600s）；（2）每帧带 `id: seq`；（3）响应头下发 `X-Stream-Id`，客户端重连时带 `X-Stream-Id` + `Last-Event-ID`；（4）服务端先回放 `seq > lastSeq` 的历史再挂到实时流，**中间存在缝隙要能检测**（回放完的最小 seq ≠ lastSeq+1 就说明事件已过期或丢失，回退为整段重传）；（5）幂等：客户端按 seq 去重，服务端 owner check 防止越权续推别人的流。
边界：生产者（LLM/工具）不能因为连接断开而停止——要么把生成任务放到连接生命周期之外（后台任务持续写日志），要么明确取消语义。本项目是前者的思路，配合 64KB/事件上限防大 payload。

**Q：Nginx 上 SSE 不出流怎么办？**
A：`proxy_buffering off`（或响应头 `X-Accel-Buffering: no`）、`proxy_read_timeout` 拉长、`chunked_transfer_encoding on`、关闭 gzip 对 `text/event-stream` 的压缩（压缩会把小帧攒住）、确认没有应用层 Filter 缓冲 body（本项目幂等 Filter 显式跳过 SSE 就是这个原因）。

**Q：HTTP/1.1 分块传输和 content-length？**
A：`Transfer-Encoding: chunked` 用 `<size>\r\n<payload>\r\n` 帧，结束于 0 长块；有 chunked 就不能同时有 Content-Length。HTTP/2 改成 DATA 帧 + 流多路复用，同域并发不再受 6 连接限制。

**Q：三次握手 / 四次挥手 / TIME_WAIT？**
A：三次为了双方确认收发能力并同步 ISN；四次挥手主动关闭方进入 `TIME_WAIT` 持续 2MSL，保证最后 ACK 可达且旧报文消散；大量 `TIME_WAIT` 来自高频短连接主动关闭 → 用长连接/连接池/调 `tcp_tw_reuse`（客户端侧）。`CLOSE_WAIT` 堆积 = 应用没关 fd，是代码 bug。半连接 SYN 队列溢出 → SYN flood 或 `syncookies`。

锚点：Redis/LLM 上游都用连接池与 keep-alive，要能说清"Lettuce 单连接多路复用 vs Jedis 池"的差别。

**P1：HTTPS/TLS1.3 握手与 0-RTT 重放风险、证书链校验、SNI；CORS 预检（`OPTIONS`、`Access-Control-Allow-Headers` 含自定义头如 `X-Stream-Id` 才需要放开）、简单请求判定；`Idempotency-Key` 幂等实现（存 key→响应，命中直接回放，TTL 1h，重试不能重复副作用）；**
**P2：TCP 拥塞控制（慢启动/拥塞避免/快重传/快恢复）、BBR、`keepalive` 与 `nagle` 对 SSE 延迟的影响、gRPC 与 HTTP/2、`SO_REUSEPORT`。**

---

## 7. 安全 【P1】

**Q：JWT 的原理和风险？和 Session 怎么选？**
A：`header.payload.signature`，HS256 对称签名（单服务）/RS256 非对称（多方验证），payload 是 Base64URL **不是加密**，别放敏感信息。优点是无状态、易水平扩展、适合 SSE 与跨端；缺点是吊销难 → 短 TTL access token + refresh token + 黑名单（Redis，用 jti），并在服务端保留登出/改密后的失效机制（本项目有 `password_resets` 类状态）。放 `localStorage` 抗 CSRF 但易被 XSS 窃取；放 `HttpOnly + Secure + SameSite` cookie 反之，配 CSRF token。

锚点：本项目的 FastAPI 语义是"缺 `Authorization` 头 → 403，token 坏/过期 → 401"（HTTPBearer 默认行为），Java 版为对拍 1:1 复刻。这题被问"为什么 401/403 不对称"，标准答案是：401 语义是"认证凭据存在但无效"（RFC 9110），403 是"未提供凭据/无权"——虽然严格说缺凭据也该 401，但框架默认如此，跨语言迁移时**契约兼容优先于自认为的正确**。

**Q：为什么用 bcrypt 而不是 SHA-256？参数怎么选？**
A：密码哈希要"慢 + 加盐 + 可调成本"。SHA-256/512 太快，GPU 每秒数十亿次，且不加盐会撞彩虹表；bcrypt 基于 Blowfish 的 EksOperative 算法，cost factor 每 +1 耗时翻倍（本项目 12 rounds），自带盐。`bcrypt` 有 72 字节输入截断（长密码要先 SHA-256 预哈希或改 Argon2id）；更优选择是 Argon2id（内存硬，抗 GPU/ASIC）；也需服务端 pepper（HMAC）与限流防爆破。跨语言哈希**互认**要验证：Java `jBCrypt` 与 Python `passlib/bcrypt` 的 `$2b$` 前缀一致才能双后端共存——这是本项目实测过的点。

**Q：SQL 注入、SSRF、越权、XSS/CSRF 怎么防？**
A：SQL 注入 → 预编译参数绑定（`JdbcTemplate` 占位符 + 类型显式 `CAST(:vec AS vector)`，向量字符串绝不拼进 SQL），排序字段/表名这类不能参数化的走白名单映射；SSRF → 出网域名/协议白名单、禁内网与元数据地址（`169.254.169.254`、`127/10/172.16`）、禁跟随重定向或每次跳转都复校验、解析后 IP 校验防 DNS rebinding（本项目在天气/图片代理侧有防护）；越权 → 每个资源操作做 owner check（水平越权）+ 角色/权限校验（垂直越权，`admin` 接口单独守卫），不要相信前端传来的 user_id；XSS → 输出转义（前端 `marked` 渲染富文本必须过 DOMPurify 或白名单）、CSP；CSRF → SameSite cookie + token。

锚点：工具层的命令注入防护是真实案例——`ht-ai` CLI 调用用 `subprocess` 列表传参（无 shell）+ 控制字符清洗，而不是拼 shell 字符串。

**P2：RBAC vs ABAC、限流作为 DoS 防护、敏感信息日志脱敏、`Secret` 管理与轮换、HTTPS/HSTS、依赖漏洞扫描（OWASP dependency-check / `cargo audit` 类比）。**

---

## 8. 限流 / 熔断 / 降级 / 幂等 【P0】

**Q：四种限流算法？**
A：固定窗口计数（实现最简单，**边界突刺**：两个窗口交界处可放过 2 倍流量）、滑动窗口（时间分桶或 Redis `ZSET` + 成员时间戳，精度更好，本项目实现）、漏桶（请求入队以恒定速率流出，**强制平滑**，不适合允许突发的场景）、令牌桶（按速率补令牌、桶容量允许突发，生产最常用，Guava `RateLimiter` 是平滑突发/预热变体）。分布式限流要原子性 → Redis + Lua（`INCR`+`EXPIRE` 或 `ZSET` 滑窗）或独立令牌服务；本地 Guava 只在单实例有效，多实例要除 N。

锚点：三处不同粒度——登录按 IP + 每分钟（防撞库）、鉴权接口按 user + 每分钟、LLM 侧按"用户小时配额 + 全局每分钟"的 **token 预算守卫**（限的是成本而不是请求数，这个说法面试官爱听）。

**Q：熔断器的状态机？**
A：CLOSED → 失败达到阈值（连续次数或滑动窗口失败率）→ OPEN（直接失败/走 fallback，不再打下游）→ 冷却时间到 → HALF_OPEN（放少量探针请求）→ 成功则 CLOSED，失败则回 OPEN。关键细节：统计窗口、最小请求数（样本太少不看失败率）、慢调用也算失败、半开时并发探针只放 1 个。

锚点：`CircuitBreaker` 是 5 连续失败 / 30s 恢复、按工具名共享实例；`ToolResilienceWrapper` 在其上组合超时 + 重试 + fallback 文案。被问 pybreaker vs 自研：自研是为了 HALF_OPEN 的探针数与埋点可控。

**Q：重试、超时、幂等三件套的关系？**
A：**只有幂等的操作才允许重试**。超时要有预算并沿调用链传递 deadline（否则上游已放弃、下游还在算）；重试必须指数退避 + jitter（避免同步重试风暴）+ 最大次数 + 只对可重试错误（5xx/超时/限流 429 才看 `Retry-After`）。非幂等写操作要用幂等键去重（`Idempotency-Key`）或业务唯一约束兜底。

**Q：降级策略怎么设计？**
A：分层：数据降级（向量召回失败→只走全文；RAG 无价→城市档位估算）、功能降级（Redis 不可用→进程内缓存 + 内存任务队列）、质量降级（技能执行失败→降级到整段重新规划 `modify`）、拒绝服务（并发溢出 429 + `Retry-After`）。**降级必须 fail-open 还是 fail-closed 要显式决定**：Embedding 这种"结果正确性依赖模型"的路径，本项目 Java 侧配 `fail-closed=true`（宁可不返回向量结果，也不返回错误 embedding），而召回路径整体是 fail-open（少一路也比全挂好）。

**Q：为什么要给缓存/任务做双后端？个人项目有必要吗？**
A：答"必要性来自依赖不可用时的用户体验"——Redis 挂了系统不能全站 500；同时要说清代价：进程内后端**多实例不共享**、无过期保证、上限 128 条，所以只能当兜底不能当主用。这种"我知道它不完美、我知道边界"的表述是最大加分项。

**P2：舱壁隔离（线程池/信号量分池）、隔离级别与资源池打满的连锁故障、SLA/SLO/错误预算、超时与重试在 SSE 场景的特殊性（重连退避 1s→2s→4s 上限 8s）、指数退避为何要加 jitter、CAP 与最终一致（本项目选 CP 还是 AP 怎么答：Redis 降级期间本质是 AP + 后续补偿）。**

---

## 9. 可观测性 / 日志 / 指标 / CI 【P1】

**Q：MDC 原理？线程池/虚拟线程下为什么会丢？**
A：MDC 是 `ThreadLocal<Map>`，日志 pattern 里 `%X{requestId}` 取值。异步任务、线程池复用、虚拟线程切换都不继承父线程 ThreadLocal → 要么用 `MDC.setContextMap(copyOf(...))` 包一层装饰器（`TaskDecorator`），要么用 JDK 21 的 `ScopedValue`（尚未普及）。丢 traceId 会让全链路日志断成两段——这是我自己踩过的点。

**Q：Prometheus 的四种指标类型？P99 怎么算？**
A：Counter（只增，查询端用 `rate()`/`increase()`）、Gauge（可增可减，如队列长度、连接数）、Histogram（分桶计数 + `sum` + `count`，服务端聚合后用 `histogram_quantile()` 算分位数，**桶边界要按预期延迟分布设计**，默认桶对 30~40s 的 LLM 长请求毫无分辨率）、Summary（客户端算分位，不能跨实例聚合）。P99 **不能求平均**，只能把分子分母相加后再算分位。拉取模型（`/metrics` + scrape），跨作业聚合用 Pushgateway。

锚点：`PrometheusMetrics` 暴露 http 请求数/时延、chat 耗时、工具调用计数；要能坦白"工具层未全部接线时部分计数器无样本"。

**Q：日志/指标/链路三者的关系？**
A：Logs 是离散事件（带 trace_id 才能串）、Metrics 是聚合数值（便宜、适合告警）、Traces 是请求在分布式组件间的 span 树（W3C `traceparent`）。三者靠 `trace_id` 关联；OpenTelemetry 统一采集。RED（Rate/Errors/Duration）用于服务，USE（Utilization/Saturation/Errors）用于资源。

**Q：Agent 这类系统怎么观测？**
A：把每一步 LLM 调用和工具调用作为 span 落库（prompt、模型、耗时、token 用量、工具入参出参、重试轮次），前端做时间线视图——本质是"自研一个简化版 LangSmith"。要强调为什么落 DB 而不是只写日志：要按 conversation/trip 维度聚合与回放、要和评测 fixture 关联。

**Q：CI 流水线怎么设计？**
A：分层快到慢——单测（秒级，无外部依赖）→ 集成测试（起 pgvector/redis service container）→ 构建产物 → 契约测试（Python/Java 对拍）→ 性能（手动触发，不阻塞合并）→ nightly eval（跑 mock 回归并与 baseline 对比，main 分支才更新基线）。要点：评测基线要版本化，否则"指标倒退"无法发现。

**P2：告警降噪与去重（本项目 `services/alert/` 有 dedup + webhook + 调度）、结构化日志字段规范、采样策略（头部采样 vs 尾部采样）、指标基数爆炸（label 别放 user_id）。**

---

## 10. 向量检索与 RAG 基础 【P0，AI 岗核心】

**Q：Embedding 是什么？双塔和交叉编码器怎么分工？**
A：双塔 bi-encoder 把 query 和 doc 各自编码成一个向量，相似度 = 余弦，**doc 向量可离线预计算 + ANN 索引**，因此召回快、精度有限；cross-encoder 把 `query [SEP] doc` 拼一起过模型输出相关性分，精度显著更高但每个候选都要过一次前向，**不可预计算**。所以标准架构是 retrieve（粗召回 top-50~100）→ rerank（精排 top-5）。

锚点：`bge-small-zh-v1.5`（512 维）做召回，`bge-reranker-base` 做 top-20 重排。追问细节：BGE 中文检索**查询侧要加指令前缀**（"为这个句子生成表示以用于检索相关文章："），文档侧不加——忘了这句会被判定为没真跑过。

**Q：余弦、内积、L2 有什么区别？归一化了吗？**
A：归一化后余弦 = 内积 = L2 单调等价。未归一化时 L2 受向量长度影响，内积受范数偏好影响。BGE 系列建议归一化 + 内积/余弦。

**Q：混合检索为什么优于单向量？RRF 公式？k 为什么取 60？**
A：向量擅长语义与同义改写，但对**专有名词、稀有词、精确匹配**（"全聚德"、"G350次高铁"）不稳；BM25/全文正好相反。融合用 RRF：`score(d) = Σ_i w_i / (k + rank_i(d))`，只用排名不用分数 → **天然规避不同检索器分数分布不可比的问题**（换成加权和就得先归一化，且分布一漂就失效）。k≈60 是原始论文的经验值，作用是削弱头部排名差距（rank 1 和 rank 2 的分差被压平），k 越小越"赢家通吃"。

锚点：本项目 fulltext 0.7 / rating 0.5 / spots_vector 0.5 / spot_docs_vector 0.3，权重按"该路对最终答案的贡献与可信度"给，且某路失败/超时就少一项，**降级后仍是合法 RRF**；另外叠了 credibility 调权（authority/freshness/agreement/citation/evidence 五维加权 0.35/0.20/0.20/0.15/0.10，写入时预计算）。

**Q：分块（chunking）策略？你项目怎么做的？**
A：常见有固定长度 + overlap、递归分隔符、语义分段、结构感知（按标题/表/记录）。**本项目是"记录级原子化"**：一条 POI 就是一个知识单元，`spots`（标量 + 摘要向量）与 `spot_docs`（维基证据文本分块）分层，因为景点介绍天然有边界，硬切反而会切断"门票/开放时间"这类字段。这题答"我按业务实体边界切，不做无脑 512 滑窗"就是加分。

**Q：RAG 的失败模式有哪些，怎么定位？**
A：分两层看。**检索层**：召回不到（分块粒度、query 与 doc 表述不匹配 → query 改写/HyDE/多查询）、召回到了但排到 K 之外（缺 rerank、embedding 域不匹配）、过滤条件把正确答案滤掉（标量谓词太严）。**生成层**：上下文塞太多导致"lost in the middle"、prompt 没要求引用而模型自由发挥、上下文超长截断。定位靠分别测：Hit@K/MRR 判检索，faithfulness/context recall 判生成，不要一上来改 prompt。

**Q：怎么抑制幻觉？**
A：可组合的手段：RAG 提供证据并要求引用、**封闭世界约束**（只能使用候选集内实体）、把"不知道"作为合法输出、结构化输出 + schema 校验、生成后确定性校验（本项目校验景点是否在候选池内）、独立模型审阅、温度与采样调整、成本字段禁止裸编（宁可标 `estimate`）。**关键表述**：确定性校验优先于 LLM 自检，因为 LLM 自检本身也会幻觉。

**Q：向量库选型？**
A：见第 4 节。补一句量化能力：pgvector 0.7+ 支持 `bit`/`halfvec` 量化与更省内存的索引，量级到亿才需要考虑（本项目 3 万，完全不需要）。

**P2：HNSW 之外的 ANN（ScaNN、Annoy、DiskANN）、nDCG@K 定义、稀疏向量（SPLADE）与多向量（ColBERT）、rerank 的延迟预算与"高分命中跳过重排"、长上下文模型是否还值得做 RAG（成本、lost in the middle、私有数据、可溯源、权限过滤 → 结论：仍需，但 chunk 质量与召回精度更重要）、多模态检索。**

---

## 11. LLM / Agent / 评测 【P0】

**Q：Transformer 的注意力是怎么算的？为什么 decoder-only 成为主流？**
A：`Attention(Q,K,V) = softmax(QKᵀ/√d_k)V`，多头把 d 切成 h 份分别学子空间；除以 √d 防点积过大把 softmax 推向饱和。self-attention 内部所有 token 互相看，cross-attention 是解码器的 query 看编码器的 key/value。生成式任务用 decoder-only + 因果掩码，训练目标简单（下一 token 预测）、易 scale，配 KV cache 做推理加速（prefill 计算所有输入 K/V，decode 每步只算一个 token → 这是"长 prompt 首字延迟高、后续输出快"的根因）。

**Q：temperature / top-p / top-k 是什么？**
A：temperature 缩放 logits（→0 近似贪心，越大越平），top-k 只在概率最大的 k 个里采样，top-p（核采样）取累积概率 ≥p 的最小集合。可复现性靠 seed + 固定版本，但供应商换模型版本、并发 batching 浮点差异都会破坏完全一致，因此评测要**多采样投票**而不是单次定论。

**Q：ReAct / Function Calling 的机制？**
A：ReAct 是 Thought→Action→Observation 循环；工程上由模型的 tool_calls 结构化输出替代手写文本解析（本项目 Java 走 langchain4j 的 streaming tool_calls，Python 走 LangChain tool binding）。要点：工具 schema 描述质量直接决定调用正确率、循环要有最大轮次（本项目技能执行 ≤10 轮）、工具返回要裁剪（长 JSON 会吃掉上下文）、并行工具调用可省轮次、失败要把错误信息回喂让模型自纠。

**Q：多 Agent 什么时候值得？怎么编排？**
A：判据是"上下文隔离 + 不同模型/权限 + 独立可评测"。本项目：Research（工具自主决策）与 Plan（创造性生成，上下文只需候选池）分离——各自 prompt 与模型温度不同，且 Research 结果可缓存复用；Orchestrator 用纯代码调度而不是让 LLM 决定流程，因为流程是固定的（少一层不确定性 = 少一类故障）。反过来说：**单 Agent 能解决就别上多 Agent**，多 Agent 的成本是上下文传递损失与故障面扩大。

**Q：上下文怎么管住不超窗？**
A：滑动窗口截断、历史摘要压缩（本项目有对话压缩 + 决策 + 偏好提取的后置任务）、外部记忆（把用户偏好落到 `User.preferences`，跨会话注入）、按需加载（Skill 的 L1/L2/L3 渐进披露就是这个思路：目录常驻、正文命中才载入、资源用到才读）、结果裁剪（工具返回只留必要字段）。要能报数量级：512 维模型、对话历史 N 轮、每轮 token 估算，以及预算守卫怎么按 token 收费维度限流。

**Q：结构化输出怎么做？解析失败怎么办？**
A：手段优先级：JSON Schema / function calling 约束 > prompt 里给 schema + few-shot > 正则/代码提取兜底。失败治理：截断修复（`repair_json`：补引号括号、去尾逗号）、一次带错误信息的重试、以及"解析失败视为 review 不通过"的闭环。**不要**在 system prompt 里塞大 JSON 当唯一约束（模型会漏字段），要字段级校验器。

**Q：LLM-as-Judge 可信吗？偏差有哪些？**
A：不够可信但有用来做趋势与回归。已知偏差：位置偏差（A/B 顺序）、冗长偏差（更长的答案更高分）、自我偏好（同族模型互评偏高）、rubric 漂移（提示词/模型版本变更导致打分不可比）、评分噪声（同一答案多次打分不同）。治理：pairwise 随机顺序、明确分档 rubric、多采样取中位/多数投票、定期与人工标注对齐一致性（Kappa）。

锚点：本项目的多采样（s1/s3）+ fixture 通过率就是最低成本治理，同时可承认"14 个 evaluator 里 4 个仍是占位，真实后端通过率 8/10"——主动交底比被挖出来强。

**Q：怎么评估一个 Agent 系统？**
A：分三层。端到端：任务成功率（fixture 通过率、pass^k 稳定性）、约束满足率（预算/饮食/宠物/天数）、成本与延迟（token、P50/P99、平均轮次）；组件层：检索指标 Hit@K/MRR、工具调用正确率与冗余率；线上：满意度点赞踩、放弃率、高分低满意样本回流成 fixture（回归资产）。关键句：**离线评测集来自线上失败样本，评测才有生命力**（本项目这个自动转换还没实现，是 TODO，可如实说）。

**Q：MCP 是什么？和 function calling 什么关系？**
A：MCP 是"工具/数据源与 Agent 运行环境之间的标准协议"，Host—Client—Server 三角色，基于 JSON-RPC 2.0，传输用 stdio 或 streamable HTTP，原语有 tools / resources / prompts。function calling 是"模型如何表达要调工具"，MCP 解决"工具如何被发现和接入"，两者互补。本项目 Python 侧手写 stdio JSON-RPC 客户端拉起 `@amap/amap-maps-mcp-server` 并把 MCP tools 动态转成 LangChain 工具。

锚点（诚实面）：Java 侧目前高德走的是 `RestTemplate` 直连 REST，不是 MCP。如果被追问就说"Java 版把 MCP 客户端列在待办，因为 REST 直连已覆盖当前用例，抽象价值暂时不明显"——**这句话本身就是工程判断力的展示**。

**Q：Agent 成本怎么降？**
A：prompt 缓存（前缀命中，DeepSeek/OpenAI 有折扣，本项目实测缓存命中显著且 conc=5 比 conc=1 更快的现象就是缓存效应）、路由到小模型（fast-path 意图识别、简单问答走轻量模型）、思考模式按场景关闭（DeepSeek reasoning token 占比 >80% 导致规划 60s+，Planner 侧关闭思考）、结果缓存与工具级语义缓存、减少轮次（并行工具调用、一次 `select_skill` 同时完成路由+规划）、上下文裁剪。

**Q：推理/训练相关基础会被问吗？**
A：AI 应用岗可能问：SFT/RLHF/DPO 的区别（对齐路径）、LoRA 低秩适配、什么是 RAG 与微调怎么选（知识频繁更新、可溯源 → RAG；风格/格式/领域语感 → 微调）、量化（INT8/INT4，权重量化 vs 激活量化，GPTQ/AWQ）、KV cache 与显存估算、并发服务（continuous batching、vLLM PagedAttention）、ONNX/TensorRT 导出（本项目走过 ONNX 导出 + tokenizer 移植，能说清 `input_ids`/`attention_mask`/`token_type_ids` 与 mean pooling + 归一化）。

**P2：LangChain 与 LangGraph 的取舍（图状态机的价值：分支多/需要 checkpoint/人审中断；本项目流程固定所以退回代码）、RAG 的 GraphRAG、embedding 微调、Agentic RAG（多轮检索/自适应检索）、prompt 注入防护（工具结果与用户输入分离、外部内容不可信标记）、模型版本回归与 A/B、多模态、HyDE 与 multi-query、长上下文与 RAG 的边界。另外 Anthropic Skill 规范、Agent 权限模式与安全边界。**

---

## 12. 前端（Vue 3 + TS）【P2，除非面全栈】

**Q：Vue 3 响应式原理？和 Vue 2 的区别？**
A：`Proxy` + `Reflect` 拦截整个对象（新增/删除属性都能感知），配合 `track`/`trigger` 与 effect 依赖收集；Vue 2 用 `Object.defineProperty`，需 `Vue.set` 且数组要 hack。`ref` 用于基本类型（`.value`）也可包对象，`reactive` 深代理对象。编译器做静态提升、patchFlag 标记动态节点、block tree 跳过静态子树，diff 用最长递增子序列优化移动。

**Q：`computed` vs `watch` vs `watchEffect`？`nextTick` 干什么？**
A：computed 惰性缓存、依赖变化才重算，需纯函数；watch 显式监听新旧值对比、可控 deep/immediate/flush；watchEffect 自动收集依赖立即执行。`nextTick` 等 DOM 更新（微任务队列），在改数据后立刻读 DOM 时需要。

**Q：Vite 为什么快？**
A：dev 用浏览器原生 ESM，按需编译不做全量 bundle，冷启动只转换入口；esbuild（Go）做依赖预构建与 TS 转译；生产用 Rollup。HMR 精确到模块。

**Q：流式渲染怎么做的？**
A：ReadableStream + TextDecoder，chunk 边界不等于帧边界 → 用缓冲区按 `\n\n` 切帧（本项目 `stream-parser.ts`），解析 `data:` JSON 后按 `type` 分派到 store；重连退避 + seq 去重；`markdown` 增量渲染注意未闭合代码块/表格的中间态。

**P2：TypeScript 泛型与工具类型、虚拟 DOM 是否必要、Pinia（本项目没用，状态在组件内——被问就答"页面级状态 + 后端为准，未引入全局 store 是刻意的，代价是多视图共享要回源"）、跨域与代理、性能（长列表虚拟滚动、`markRaw` 大对象）、无障碍与 SSR。**

---

## 13. 算法与数据结构（面试现场可能被点到的）

行程规划本质是带时间窗的路线规划：**TSP / VRPTW** 是 NP-hard，实践用贪心 + 启发式（最近邻 + 2-opt / or-opt 局部搜索）、聚类分区（分城市/分片区再日内优化）、高德距离矩阵 API 代替欧氏距离；评测里 MRR、Hit@K、nDCG 的公式要能手写；RRF 要能现场推导。限流/幂等/队列相关的数据结构（滑动窗口用 `ZSET`、优先队列用 `BZPOPMIN`、消费者组用 Stream PEL）也要能画图讲。

---

## 14. 复习顺序建议

1. 先吃透第 1、6、8、10、11 节——这四节直接对应简历上最亮的五条 bullet，被追问概率最高。
2. 第 4、5 节用"我项目里这张表/这个 key 为什么这么设计"来记，比背概念快。
3. 第 2、3 节是 Java 岗基本盘，重点是 `@Transactional` 失效、N+1、Bean 生命周期、代理。
4. 每次回答都收一句"代价/边界"——个人项目最容易被质疑"你这规模有意义吗"，主动承认边界比辩解强。

## 15. 这份稿子里三处"措辞需与代码对齐"的提醒

- **虚拟线程**：Spring Boot 的 `spring.threads.virtual.enabled` 当前未在 `application.yml` 打开，也就是说 Web 请求线程仍是 Tomcat 平台线程，虚拟线程只用在模型预热与异步任务。别答成"整个应用跑在虚拟线程上"。
- **MCP**：Java 侧高德是 REST 客户端，Python 侧才是手写 JSON-RPC MCP。
- **评测**：4 个 evaluator 占位、检索评测集为 mock，讲的时候要带上这个前提。
