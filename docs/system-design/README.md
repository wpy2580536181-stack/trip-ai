# 系统设计面试答案（trip 项目）

> 3 篇系统设计题的答卷，每篇 1500 字左右，按"QPS 估算 → 存储选型 → 关键流程 → 难点 → 故事"标准结构。
> 答：基于本项目真实代码事实（`trip-backend/src/`），不是空口背答案。

## 目录

| # | 题目 | 对应项目代码 | 关键能力点 |
|---|---|---|---|
| [01](./01-rate-limiter.md) | 分布式限流器设计 | `src/middleware/rate_limiter.py` | 4 种算法对比 / 5 层限流 / 双后端降级 / 响应头 |
| [02](./02-rag-search.md) | 多路召回 RAG 搜索 | `src/services/knowledge_service.py:search_spots` | 4 路并行 / RRF 融合 / Cross-Encoder 重排 / 证据回挂 |
| [03](./03-trip-recommend.md) | 行程推荐 Feed 系统 | `src/services/trip_service.py:recommend` | 5 层保护 / agent 编排 / enrich 并行 / 流式 SSE / 失败降级 |

## 使用方式

1. **面试前 1 周**：每篇读 3 遍，**用自己的话复述讲故事模板（每篇第 8/9 节）**
2. **面试中**：面试官问"系统设计题"时，**主动说"我项目里有真实实现"**，然后引导到对应文档
3. **细节追问**：答不上的细节诚实说"这块我项目用得简单，背后原理我看过但没亲手实现"

## 不在 3 篇里的（面试次高频）

| 题目 | 现状 | 建议 |
|---|---|---|
| **短链系统** | 项目无 | 读《系统设计之美》第 4 章 |
| **Feed 流（Twitter）** | 项目无 | 读《数据密集型》第 5 章 |
| **秒杀系统** | 项目无 | 面试前速记"预扣 + 限流 + 兜底" |
| **IM 系统** | 项目无 | 面试前速记"WebSocket + 消息可靠投递" |
| **分布式锁** | 项目**不做**（已决策） | 诚实说"YAGNI，用单进程/CronJob 替代" |
| **一致性 hash** | 项目无 | 读 1 篇博客 + 画图说明 |

## 配套能力

| 能力 | 文档 | 故事性 |
|---|---|---|
| 消息队列（arq） | [task-queue-tech-decision.md](../task-queue-tech-decision.md) | 进程崩溃不丢任务 |
| 可观测性（熔断/Prom/慢查询） | 同上 §11 | "3 类信号组合" |
| 缓存（Redis 降级内存） | `poi_cache.py` 双后端范式 | 热点 key 击穿/雪崩 |
| 数据库索引 | `src/models/*.py` 8 复合 + 2 FULLTEXT | B+Tree + 倒排 |

---

**面试前必读 4 份文档（按优先级）**：
1. `task-queue-tech-decision.md` §0 TL;DR（5 分钟看完全局）
2. `01-rate-limiter.md` §0 + §8（10 分钟）
3. `02-rag-search.md` §0 + §8（10 分钟）
4. `03-trip-recommend.md` §0 + §9（10 分钟）

**总计 35 分钟读完，足够应付 80% 的后端/系统设计面试追问。**
