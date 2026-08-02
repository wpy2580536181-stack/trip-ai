# 生产压测报告 设计

> 配套 `docs/interview-plan.md` 亮点 3、`docs/agent-improvements.md` §2.4
> Week 3（2026-07-06 ~ 2026-07-12）

## 目标

用**真实数据**回答"服务能扛多少？"——产出 1 份压测报告 + 6 张图表 + README 5 数字。面试能直接讲：

> "我的服务在 100 并发 SSE 流式下 P99 是 X 秒，单实例普通 API QPS 达 Y，LLM 缓存命中率 Z%。"

---

## 范围

### In Scope

1. **4 个压测场景**：
   - **普通 HTTP**：登录 / 查历史（`/api/user/login`, `/api/history`）
   - **SSE 流式 chat**：`/api/trip/chat`（核心卖点）
   - **LLM 路由**：`/api/trip/recommend`（最重的同步接口）
   - **缓存效果**：50 个相似问题跑 `/stats/token-usage/logs` 测命中率

2. **6 张图表**（chart.js 静态图）：
   - QPS-P99 曲线（普通 HTTP）
   - SSE 并发 vs 流延迟
   - LLM token/s 分布
   - 缓存命中率 vs 请求数
   - CPU/内存随并发变化
   - P50/P95/P99 对比

3. **报告文档** `docs/performance-benchmark.md`：
   - 压测环境（机器配置 / Node 版本 / MySQL 版本）
   - 4 个场景的方法 + 数据 + 结论
   - 6 张图表嵌入
   - 瓶颈分析（哪个环节慢）
   - 优化建议（按 ROI 排序）

4. **README 更新**：
   - 加 "Performance" 章节
   - 5 个关键数字（QPS / P99 / 并发 / 缓存命中率 / token 节省）

5. **压测脚本** `trip-server/scripts/benchmark/`：
   - `benchmark-http.ts`（autocannon wrapper）
   - `benchmark-sse.ts`（k6 script）
   - `benchmark-llm.ts`（自定义 runner）
   - `benchmark-cache.ts`（50 相似问题）
   - `chart-render.ts`（用 chart.js-node-canvas 生成 PNG）

6. **原始数据存档** `docs/performance-data/`：
   - `http-results.json`
   - `sse-results.json`
   - `llm-results.json`
   - `cache-results.json`

### Out of Scope

- ❌ 优化代码（瓶颈发现后只记录建议，不改）
- ❌ 多实例压测（单实例足够，K8s 留给生产）
- ❌ 长时间压测（5min 短跑足够 demo）
- ❌ 多种 LLM provider 对比（DeepSeek 单一）
- ❌ 网络层压测（CDN/带宽）

---

## 架构

### 1. 文件结构

```
trip-server/
├── scripts/
│   └── benchmark/
│       ├── benchmark-http.ts        # autocannon 包装
│       ├── benchmark-sse.ts         # k6 脚本 + Node 触发器
│       ├── benchmark-llm.ts         # 顺序跑 10 次 /recommend
│       ├── benchmark-cache.ts       # 50 相似问题
│       ├── chart-render.ts          # 图表生成
│       ├── lib/
│       │   ├── http-client.ts       # fetch + metrics
│       │   └── result-store.ts      # 写 results/*.json
│       └── run-all.ts               # 主入口：跑 4 个场景 + 图表
docs/
├── performance-benchmark.md         # NEW 主报告
├── performance-data/                # NEW 原始数据
│   ├── http-results.json
│   ├── sse-results.json
│   ├── llm-results.json
│   ├── cache-results.json
│   └── charts/                      # NEW 6 张 PNG
│       ├── qps-p99.png
│       ├── sse-concurrency.png
│       ├── llm-tokens.png
│       ├── cache-hitrate.png
│       ├── resources.png
│       └── p-percentiles.png
README.md                            # UPDATE 加 Performance 章节
trip-server/package.json             # +依赖：autocannon、k6（仅 CLI）、chartjs-node-canvas
```

### 2. 压测方法

#### 场景 1：普通 HTTP（autocannon）

```bash
# 登录接口
npx autocannon -c 10 -d 30 -j \
  -H "Content-Type: application/json" \
  -b '{"username":"eval-test","password":"EvalTest@2026"}' \
  http://localhost:3000/api/user/login
```

记录：QPS / P50 / P99 / 错误率

#### 场景 2：SSE 流式（k6）

```javascript
// k6/sse.js
import http from 'k6/http'
import { check } from 'k6'

export const options = {
  scenarios: {
    sse_load: {
      executor: 'constant-arrival-rate',
      rate: 10, timeUnit: '1s', duration: '30s', preAllocatedVUs: 50,
    },
  },
  thresholds: { http_req_duration: ['p(99)<5000'] },
}

export default function () {
  const res = http.post(`${__ENV.BASE_URL}/api/trip/chat`,
    JSON.stringify({ message: '上海 2 天美食' }),
    { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${__ENV.TOKEN}` } }
  )
  check(res, { 'status 200': r => r.status === 200 })
}
```

#### 场景 3：LLM 路由（自定义）

```typescript
// benchmark-llm.ts
for (let i = 0; i < 10; i++) {
  const start = Date.now()
  const res = await fetch('/api/trip/recommend', {...})
  const tokens = await readSSEAndCountTokens(res)
  metrics.push({ duration: Date.now() - start, prompt: tokens.prompt, completion: tokens.completion })
}
```

#### 场景 4：缓存效果（50 相似问题）

```typescript
// benchmark-cache.ts
const questions = [
  { city: '北京', days: 2, budget: 3000 },
  { city: '北京', days: 3, budget: 5000 },  // 相似但不完全一样
  { city: '上海', days: 2, budget: 3000 },
  // ... 50 个
]
for (const q of questions) {
  await fetch('/api/trip/recommend', { body: JSON.stringify(q) })
}
// 然后 GET /api/stats/token-usage/logs 算命中率
```

### 3. 指标收集

每个场景输出 JSON：
```json
{
  "scenario": "http-login",
  "durationSec": 30,
  "concurrency": 10,
  "totalRequests": 3000,
  "qps": 95.3,
  "latency": { "p50": 12, "p95": 28, "p99": 45, "max": 120 },
  "errors": 0,
  "timestamp": "2026-07-08T10:00:00Z",
  "env": { "node": "v22.0.0", "cpu": "Apple M1 Pro 8-core", "mem": "16GB" }
}
```

### 4. 图表生成

用 `chartjs-node-canvas`（Node 版 chart.js）生成 PNG：

```typescript
// chart-render.ts
import { ChartJSNodeCanvas } from 'chartjs-node-canvas'

async function renderQpsP99(data) {
  const chart = new ChartJSNodeCanvas({ width: 800, height: 400 })
  return await chart.renderToBuffer({
    type: 'line',
    data: { labels: data.concurrencies, datasets: [
      { label: 'QPS', data: data.qps, yAxisID: 'y' },
      { label: 'P99 (ms)', data: data.p99, yAxisID: 'y1' },
    ] },
    options: { scales: { y: { position: 'left' }, y1: { position: 'right' } } }
  })
}
```

### 5. 报告模板

```markdown
# 生产压测报告

## 环境
- 机器：Apple M1 Pro 8-core / 16GB
- Node.js：v22.0.0
- MySQL：8.0（本地 docker）
- Chroma：latest（本地 docker）
- Redis：7-alpine（本地 docker）
- DeepSeek：deepseek-v4-flash

## 关键数字（5 个）

| 指标 | 数值 | 条件 |
|---|---|---|
| 单实例 QPS | X | 10 并发 / 普通 HTTP |
| SSE P99 | X 秒 | 100 并发 / 流式 chat |
| LLM 缓存命中率 | X% | 50 相似问题 |
| 平均 token/chunk | X | streaming |
| CPU 峰值 | X% | 100 并发 SSE |

## 场景 1：普通 HTTP

[数据表 + 图表]

## 场景 2：SSE 流式

[数据表 + 图表]

## 场景 3：LLM 路由

[数据表 + 图表]

## 场景 4：缓存效果

[数据表 + 图表]

## 瓶颈分析

| 环节 | 占比 | 优化建议 |
|---|---|---|
| Chroma 向量检索 | 60% | 加 Redis 缓存（待做）|
| LLM 调用 | 30% | prompt cache 已用 |
| 序列化 | 5% | - |
| DB | 5% | 已加索引 |

## 面试话术

> "我的服务在 100 并发 SSE 流式下 P99 是 X 秒..."
```

---

## 实施步骤

1. **装依赖** + 写 `result-store.ts` 工具
2. **benchmark-http.ts** + 跑 + 存结果
3. **benchmark-sse.ts** + 跑 + 存结果
4. **benchmark-llm.ts** + 跑 + 存结果
5. **benchmark-cache.ts** + 跑 + 存结果
6. **chart-render.ts** + 生成 6 张 PNG
7. **docs/performance-benchmark.md** 写报告
8. **README.md** 加 Performance 章节
9. **Commit + push**

---

## 风险与缓解

| 风险 | 缓解 |
|---|---|
| k6 安装复杂 | 用 Node 触发 + 简化版并发（不严格用 k6）|
| LLM 真实调用慢/贵 | 只跑 10 次 / 复用 fixture 数据 |
| chart.js-node-canvas 装不上 | 降级到纯 ASCII 表格 + 文字图 |
| 机器性能差异 | 报告明确写环境，结论以相对值（"X% 提升"）|

---

## 验证标准

1. `pnpm benchmark` 一键跑全部 4 场景
2. `docs/performance-data/*.json` 4 个文件都有数据
3. `docs/performance-data/charts/*.png` 6 张图都生成
4. `docs/performance-benchmark.md` 完整（含 5 数字 + 4 场景 + 6 图 + 瓶颈）
5. README "Performance" 章节有 5 数字
6. typecheck 双端 clean

---

## 关键决策

1. **完整方案**（4 场景 + 报告 + 图表）
2. **autocannon** 普通 HTTP + **k6** SSE + **自定义** LLM
3. **chartjs-node-canvas** 生成 PNG（不依赖外部工具）
4. **原始数据存档**（docs/performance-data/）—— 面试可引用
5. **瓶颈只记录不优化**（节省时间，优化留给 Week 4 或面试后）
6. **环境明确**（机器/Node/MySQL 版本都写清楚）
7. **README 5 数字**（最常被引用的部分）
