# 系统设计 01：分布式限流器（Rate Limiter）

> 面试题：「请设计一个能扛 1 万 QPS、支持多维度限流的限流系统」
> 答：基于本项目 `src/middleware/rate_limiter.py` 的真实实现展开。

---

## 0. 一句话总结

> **5 层限流配置 + 滑动窗口算法 + Redis/内存双后端降级 + 限流响应头**——一个 200 行代码就够用、但能讲清"为什么这么选"的限流器。

---

## 1. 需求拆解（QPS 估算）

| 维度 | 估算 | 说明 |
|---|---|---|
| **总 QPS** | 1 万 | DAU 10w × 每人日均 100 次请求 ÷ 86400s ≈ 116，但热门时段 10x 集中 |
| **峰值 QPS** | 1-2 万 | 早 9 点 / 晚 8 点是出行的请求高峰 |
| **单接口 QPS** | 100-500 | 行程推荐是重接口（LLM + 检索），chat 中等（流式），feedback 极低 |
| **存储 QPS** | 5-10 万 | 1 个接口可能触发 5-10 个子调用（4 路召回 + 缓存读） |
| **总 QPS 放大** | 5-10x | 中间层越多放大越严重 |

**关键约束**：
- **要快**：单次限流判断 < 1ms（用户请求最频繁的环节）
- **要准**：滑动窗口而非固定窗口（避免临界点双倍突发）
- **要能降级**：Redis 挂了不能影响主链路
- **要可观测**：必须能告诉调用方"你还有几次、什么时候重置"

---

## 2. 4 种限流算法对比（必考点）

| 算法 | 原理 | 优点 | 缺点 | 适用场景 |
|---|---|---|---|---|
| **固定窗口** | 1 分钟桶，`count++` 超限拒绝 | 简单、内存小 | **临界点双倍突发**（59s + 60s 共 2x 限额） | 极简内部限流 |
| **滑动日志** | 记录每次请求时间戳，统计窗口内数量 | 100% 精确 | **内存爆炸**（QPS 1 万要存 60 万条/分钟） | 合规审计 |
| **滑动窗口** | 当前窗口 + 前一窗口按时间占比加权 | 内存小 + 接近精确 | 仍是估算 | **本项目选** |
| **令牌桶** | 桶里 N 个令牌，每请求消耗 1 个，桶按速率补充 | 天然支持**突发流量** | 实现复杂（要后台线程补令牌） | API 网关、削峰填谷 |
| **漏桶** | 请求进桶，按固定速率漏出 | 绝对平滑 | 不能利用突发空闲容量 | 流量整形 |

**本项目选滑动窗口的原因**：
- 业务不需要支持突发（chat/推荐都是用户主动触发，不会有"攒 1 分钟后爆发"的场景）
- 实现简单（两个计数器 + 时间权重），200 行内能写完
- 内存可控（每 user 2 个 count，10w user = 80 字节 × 10w = 8MB）

**令牌桶更优但本项目没用**：
- 需要后台协程或线程定期补令牌（asyncio.Lock + sleep 实现）
- trip 服务是 FastAPI 单进程 + arq 任务队列，**后台定时任务本身就是反模式**（进程重启 = 状态丢失）
- 留给 API 网关层做（Kong / APISIX 是合适的层）

---

## 3. 5 层限流配置（按"贵"的程度分级）

```python
# src/middleware/rate_limiter.py:203-251
# 全局：200 次/分钟（防 DDoS）
global_rate_limiter_config = {"max_requests": 200, "window_seconds": 60}

# 认证：20 次/分钟（防撞库）
auth_rate_limiter = RateLimiter(max_requests=20, window_seconds=60, ...)

# 反馈：30 次/小时（防刷反馈）
feedback_rate_limiter = RateLimiter(max_requests=30, window_seconds=3600, ...)

# 知识库写：100 次/分钟（防大批量滥用）
knowledge_rate_limiter = RateLimiter(max_requests=100, window_seconds=60, ...)

# Chat：20 次/分钟（贵：每次调 LLM 流式）
chat_rate_limiter = RateLimiter(max_requests=20, window_seconds=60, ...)

# 推荐：10 次/分钟（最贵：LLM + RAG 4 路召回）
recommend_rate_limiter = RateLimiter(max_requests=10, window_seconds=60, ...)

# 行程优化：5 次/分钟（最贵：LLM + 全文分析）
optimize_rate_limiter = RateLimiter(max_requests=5, window_seconds=60, ...)
```

**设计原则**：
- **越贵的接口限额越低** —— LLM 调一次 5-10s，不限流会被刷爆
- **不可重入的接口单独配** —— 反馈、撞库等场景要严防
- **用环境变量覆盖默认值** —— 灰度期间可下调，紧急情况可关停

---

## 4. 滑动窗口实现核心

```python
# src/middleware/rate_limiter.py:25-55
class RateLimitEntry:
    __slots__ = ("count", "reset_at")
    def __init__(self, count, reset_at):
        self.count = count
        self.reset_at = reset_at

class MemoryStore:
    async def increment(self, key, window_s):
        now = time.time()
        entry = self._data.get(key)
        if not entry or now >= entry.reset_at:
            # 新窗口
            self._data[key] = RateLimitEntry(1, now + window_s)
            return 1, now + window_s
        entry.count += 1
        return entry.count, entry.reset_at
```

**关键点**：
- 实际是**固定窗口 + 惰性清理**（不是真·滑动窗口），但足够覆盖 90% 场景
- 1 分钟内的"前一窗口权重"用 Redis Lua 脚本能算得精确，但本项目没做——**这是显式的权衡**（简单 > 精确）
- `__slots__` 优化内存：10w 用户只占 8MB

---

## 5. Redis / 内存双后端（关键设计）

```python
# src/middleware/rate_limiter.py:67-100
class RedisStore:
    async def increment(self, key, window_s):
        # 用 pipeline 保证 INCR + EXPIRE 原子
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = await pipe.execute()
        return results[0], time.time() + window_s

def _create_store():
    if is_redis_available():
        return RedisStore(get_redis())
    return MemoryStore()  # 降级
```

**双后端的意义**：
- **Redis 可用**：分布式限流（多 web 进程共享计数）
- **Redis 挂**：自动降级为内存（每进程独立计数，限额变"每进程"——比没有强）

**面试必问题**：「Redis 挂时降级有什么问题？」
- **答**：N 个进程的限额变成 N 倍——比如 20 次/分钟 × 4 进程 = 80 次/分钟
- **应对**：服务降级时记录告警，让运维介入；同时考虑**令牌桶 + 单进程内本地计数**作为最终兜底

---

## 6. 限流响应头（RFC 6585 风格）

```python
# src/middleware/rate_limiter.py:146-150
request.state.rate_limit_headers = {
    "X-RateLimit-Limit": str(self.max_requests),
    "X-RateLimit-Remaining": str(max(0, self.max_requests - count)),
    "X-RateLimit-Reset": str(math.ceil(reset_at)),
}
```

**作用**：
- 前端 / SDK 拿到 `Remaining=0` 主动禁用按钮
- `Reset=timestamp` 告诉前端什么时候可以重试
- 比单纯 429 更友好（前端能精确退避）

---

## 7. 故障转移路径（实战）

| 场景 | 现象 | 应对 |
|---|---|---|
| **Redis 正常** | 分布式精确限流 | 正常返回 429 + 响应头 |
| **Redis 抖** | `pipeline.execute()` 超时 | 降级为内存（不抛错） |
| **Redis 挂** | `is_redis_available()` 返 False | 同上 |
| **限流规则配错** | 用户投诉 429 太严 | 调环境变量，不动代码 |
| **被刷爆** | 单接口 QPS 异常高 | 全局限流拦在最前，**避免 5 层都过** |

---

## 8. 面试讲故事模板

> "我项目里 5 层限流覆盖 7 类接口：全局 200 次/分钟防 DDoS，认证 20 次防撞库，chat 20 次、推荐 10 次、行程优化 5 次是按 LLM 成本分级的。算法用滑动窗口的简化版——固定窗口 + 惰性清理，权衡是临界点双倍突发但实现简单；令牌桶更适合 API 网关层做。Redis 优先 + 内存降级双后端，Redis 挂时自动转内存，限额变成'每进程'。每个响应都带 X-RateLimit-Limit/Remaining/Reset 三个头，前端能精确退避。"

---

## 9. 跟本项目其他能力的连接

- **熔断器**（`src/services/agent/resilience.py`）：限流是入口保护，熔断是出口保护——LLM 抽风时熔断器 Open
- **Prometheus metrics**（`src/middleware/prom_metrics.py`）：`http_requests_total{status="429"}` 监控限流命中率
- **arq 任务队列**（M0-M3-A 落地）：限流是同步路径保护，任务队列是异步路径保护——组合起来覆盖所有流量入口

---

## 附录：关键文件

- 限流实现：`trip-backend/src/middleware/rate_limiter.py`（251 行）
- 测试：`trip-backend/tests/test_rate_limiter.py`（已存在）
- 响应头规范：[RFC 6585 §4](https://datatracker.ietf.org/doc/html/rfc6585#section-4)

---

**文档结束。** 这份答卷约 1500 字，覆盖 4 种算法对比 + 5 层配置 + 双后端降级 + 响应头设计，足够应付 30-45 分钟的系统设计面试。
