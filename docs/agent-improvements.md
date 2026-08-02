# Agent 项目改进方案

> 从 **产品完整性**、**工程化深度**、**架构成熟度** 三个维度，对当前 AI Agent 旅行规划项目提出的系统化改进建议。

---

## 目录

- [一、产品层面](#一产品层面)
  - [1.1 行程导出](#11-行程导出)
  - [1.2 多模态识别](#12-多模态识别)
  - [1.3 行程协作](#13-行程协作)
  - [1.4 推送通知](#14-推送通知)
  - [1.5 离线支持 (PWA)](#15-离线支持-pwa)
- [二、工程化层面](#二工程化层面)
  - [2.1 测试体系](#21-测试体系)
  - [2.2 可观测性](#22-可观测性)
  - [2.3 评估体系](#23-评估体系)
  - [2.4 CI/CD](#24-cicd)
  - [2.5 安全加固](#25-安全加固)
  - [2.6 缓存策略](#26-缓存策略)
- [三、架构层面](#三架构层面)
  - [3.1 LangGraph 替代 AgentExecutor](#31-langgraph-替代-agentexecutor)
  - [3.2 多 Agent 协作](#32-多-agent-协作)
  - [3.3 语义缓存](#33-语义缓存)
  - [3.4 流式方案升级](#34-流式方案升级)
  - [3.5 混合检索升级](#35-混合检索升级)
  - [3.6 Agent 即服务](#36-agent-即服务)

---

## 一、产品层面

### 1.1 行程导出

**现状**：行程只能在网页端查看，用户到了目的地无法离线使用。

**方案**：

| 导出格式 | 实现方式 | 技术栈 |
|---|---|---|
| PDF | 服务端 puppeteer 渲染生成，或前端 html2canvas + jsPDF | `puppeteer`, `jsPDF` |
| iCalendar | 按天生成事件，导出 .ics 文件，可导入手机日历 | `ics` npm 包 |
| 分享链接 | 生成临时 token，7 天有效，无需登录即可查看 | JWT + 短链接 + TTL |

**关键实现点**：
- PDF 模板用 HTML/CSS 设计，复用 Detail.vue 的布局
- 服务端 puppeteer 渲染时注入 CSS `@page { margin: 0; size: A4 }`
- 分享链接用 `crypto.randomUUID()` 生成 token，存 `Share` 表（tripId + token + expiresAt）

---

### 1.2 多模态识别

**现状**：仅支持文本交互。

**方案**：用户上传景点/食物/标识照片 → Agent 调用 vision 模型识别 → RAG 检索详细信息。

```
┌─ 前端 ───────────────────────────────┐
│  Chat.vue: van-uploader → 图片文件    │
│  POST /api/chat (multipart/form-data) │
└───────────────┬──────────────────────┘
                ↓
┌─ 后端 ─────────────────────────────────┐
│  1. 上传到本地/OSS 存储                │
│  2. vision 模型分析图片:               │
│     选项A: GPT-4V / Claude Vision     │
│     选项B: 本地 clip-ViT 识别地标      │
│  3. 提取实体名 → 调用 retrieve_knowledge │
│  4. 组合回答 + 图片 URL 返回           │
└────────────────────────────────────────┘
```

**新增 Tool**：
```typescript
export const analyzeImageTool = withResilience(
  new DynamicStructuredTool({
    name: 'analyze_image',
    description: '分析用户上传的旅行照片，识别景点/美食/标识并返回详细信息',
    schema: z.object({
      imageUrl: z.string().describe('图片 URL'),
      question: z.string().optional().describe('用户对图片的具体问题'),
    }),
    func: async (input) => {
      // 调用 vision API（DeepSeek-VL / Qwen-VL / GPT-4V）
      const vision = createVisionLLM()
      const result = await vision.invoke([new HumanMessage({
        content: [
          { type: 'image_url', image_url: input.imageUrl },
          { type: 'text', text: input.question || '这张图片里是什么地方？有什么值得了解的？' },
        ],
      })])
      return result.content as string
    },
  }),
  { timeout: 15000, retries: 1, fallback: '图片暂时无法识别，请描述你想了解的内容' },
)
```

**其他多模态场景**：
- 语音输入 → 前端 `Web Speech API` 或 Whisper 转文字 → 正常 Agent 流程
- 地图标注 → 用户在地图上圈选区域 → Agent 规划该区域内路线

---

### 1.3 行程协作

**现状**：单人使用。

**方案**：创建旅行小组，成员可共同编辑和评论行程。

**数据库扩展**：
```prisma
model TripGroup {
  id        Int     @id @default(autoincrement())
  tripId    Int     @map("trip_id")
  inviteCode String  @unique @db.VarChar(20) @map("invite_code")
  members   TripGroupMember[]
  @@map("trip_groups")
}

model TripGroupMember {
  id        Int      @id @default(autoincrement())
  groupId   Int      @map("group_id")
  userId    Int      @map("user_id")
  role      String   @default("member")      // "owner" | "editor" | "viewer"
  joinedAt  DateTime @default(now())
  @@map("trip_group_members")
}

model TripComment {
  id        Int      @id @default(autoincrement())
  tripId    Int      @map("trip_id")
  userId    Int      @map("user_id")
  dayIndex  Int?     @map("day_index")        // 评论针对某一天的安排
  spotName  String?  @map("spot_name")        // 或针对某个景点
  content   String   @db.Text
  createdAt DateTime @default(now())
  @@map("trip_comments")
}
```

**实时同步**：
- **方案 A**：WebSocket (`ws` npm 包) → 行程变更时广播给所有在线成员
- **方案 B**：轮询（简单，适合 Phase 1）→ 每 5s 检查 `trip.updatedAt` 是否变化
- **并发编辑冲突**：乐观锁（`version` 字段 + 提交时检查 `WHERE version = ?`）

**新增 API**：
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/trip/:id/share` | 生成邀请链接 |
| POST | `/api/trip/:id/join` | 通过邀请码加入 |
| GET | `/api/trip/:id/members` | 查看小组成员 |
| POST | `/api/trip/:id/comments` | 添加评论 |

---

### 1.4 推送通知

**现状**：无通知机制。

**方案**：

| 场景 | 触发条件 | 通知内容 |
|---|---|---|
| 出发提醒 | 行程中第 1 天 08:00 | "今天是{城市}行程的第 1 天！查看今日安排" |
| 天气预警 | Agent 检测到目的地暴雨/台风 | "{城市}明天有大雨，建议调整户外行程" |
| 行程优化完成 | AI 优化生成新版本 | "你的{城市}行程已优化，点击查看新版本" |

**技术方案**：
- **浏览器端**：Service Worker + Web Push API + VAPID 密钥
- **App 端**（如后续做 RN/Flutter）：Firebase Cloud Messaging
- **后端**：`node-cron` 定时扫描今日出发的行程 + 调用 `get_weather` 检查预警

---

### 1.5 离线支持 (PWA)

**现状**：纯 SPA，离线完全不可用。

**方案**：
- `vite-plugin-pwa` + `workbox` 生成 Service Worker
- 缓存策略：HTML (NetworkFirst)、静态资源 (CacheFirst)、API (NetworkOnly)
- 离线状态：显示已缓存的行程列表 + "离线模式"标识
- IndexedDB 存储已加载的行程 JSON 数据

---

## 二、工程化层面

### 2.1 测试体系

**现状**：0 个自动化测试。

**方案**：

#### 单元测试（`vitest`）

```bash
trip-server/src/__tests__/
├── utils/
│   ├── jsonExtractor.test.ts        # 边界：空字符串、嵌套 JSON、markdown 包裹
│   ├── params.test.ts               # parseIntParam 各种非法输入
│   └── stream.test.ts               # SSE payload 序列化
├── services/
│   ├── knowledgeService.test.ts     # mock Chroma，验证降级逻辑
│   ├── conversationService.test.ts  # 滑动窗口边界、loadContext 逻辑
│   ├── summaryService.test.ts       # 阈值判断、空对话
│   └── agent/
│       ├── resilience.test.ts       # mock tool，验证超时/重试/降级
│       ├── extractTokenText.test.ts # 各种 StreamEvent 格式
│       └── tools/
│           ├── retrieveKnowledge.test.ts
│           ├── calculateDistance.test.ts  # 同一城市、不存在的城市
│           └── getWeather.test.ts         # mock fetch
└── controllers/
    ├── knowledge.test.ts
    └── history.test.ts
```

#### RAG 评估（`ragas`）

构建评估数据集：

```typescript
const evalDataset = [
  {
    question: "成都必去景点有哪些",
    groundTruth: ["武侯祠", "宽窄巷子", "大熊猫基地"],
    context: knowledgeService.searchSpots({ query: "成都必去景点", city: "成都" }),
  },
  // ... 50+ 条
]
```

评估指标：
- **Context Precision**：检索结果中相关文档的比例
- **Context Recall**：ground truth 中有多少被检索出来
- **Faithfulness**：LLM 回答是否基于检索结果（而非幻觉）
- **Answer Relevancy**：回答与问题的语义相关性

#### Agent 行为测试

```typescript
test('询问天气时应调用 get_weather tool', async () => {
  const events: AgentStreamEvent[] = []
  await agentEngine.chat({
    userId: 1,
    message: '北京今天天气怎么样',
    onEvent: async (e) => events.push(e),
  })
  const toolCalls = events.filter(e => e.type === 'tool_start')
  expect(toolCalls.some(t => t.name === 'get_weather')).toBe(true)
})

test('推荐行程应输出合法 JSON', async () => {
  const result = await agentEngine.recommend({
    userId: 1,
    city: '北京',
    budget: 3000,
    days: 3,
    onEvent: async () => {},
  })
  expect(() => TripContentSchema.parse(result.parsed)).not.toThrow()
})
```

---

### 2.2 可观测性

**现状**：`console.log` 散落各处，无法联调或线上定位。

**方案**：

#### 结构化日志（`pino`）

```typescript
import pino from 'pino'
export const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  transport: { target: 'pino/file', options: { destination: './logs/app.log' } },
})

// 使用
logger.info({ conversationId, messageLen: message.length }, '开始 Agent 对话')
logger.warn({ toolName, attempt, errMsg }, 'Tool 第 N 次失败')
logger.error({ err, rawOutput: rawOutput.slice(0, 200) }, 'Agent JSON 解析失败')
```

#### 分布式追踪（`OpenTelemetry`）

一次 chat 请求的完整链路：

```
POST /api/trip/chat (2.3s 总耗时)
├── getOrCreateConversation: 42ms
├── loadContext: 15ms
├── agentEngine.chat: 2.1s
│   ├── [LLM think] 0.8s
│   ├── retrieve_knowledge: 0.6s
│   │   ├── rewriteQuery: 0.2s
│   │   ├── embedText: 0.15s
│   │   ├── chroma.query: 0.05s
│   │   └── rerankTopK: 0.1s
│   └── [LLM answer] 0.7s
└── persistAssistant: 30ms
```

**实现**：
```typescript
import { trace, SpanStatusCode } from '@opentelemetry/api'
const tracer = trace.getTracer('trip-server')

const span = tracer.startSpan('agentEngine.chat')
try {
  // ... chat logic ...
  span.setAttribute('conversationId', conversationId)
  span.setAttribute('messageLength', message.length)
} catch (e) {
  span.setStatus({ code: SpanStatusCode.ERROR, message: e.message })
} finally {
  span.end()
}
```

#### Agent 轨迹回放（`LangFuse` / `LangSmith`）

接入 LangFuse 记录每次 Agent 执行：
- 输入：用户消息
- 每一步：Thought → Action → Observation → Final Answer
- 输出：LLM 回复 + token 消耗 + 耗时
- 反馈：用户点赞/踩标记

面试可展示的 dashboard：
- Token 消耗趋势
- Tool 调用频率分布
- 错误率走势

> ✅ **部分完成 2026-06-25**：agent trace 持久化（AgentStep 表 + admin 可视化时间轴页面）已交付。完整 OpenTelemetry + trace ID 关联待后续。

---

### 2.3 评估体系

**现状**：依赖人工测试。

**方案**：建立"离线评估 → 在线反馈 → 持续优化"闭环。

#### 离线评估

```
数据集构建 → 
  跑一批标准问题 → 
    Agent 输出 vs Ground Truth → 
      ragas 指标报表
```

数据集示例：
```json
{
  "query": "成都三日游，预算3000",
  "expected": {
    "city": "成都",
    "days": 3,
    "shouldContain": ["武侯祠", "宽窄巷子", "大熊猫基地"],
    "budgetInRange": [2500, 3500]
  }
}
```

#### 在线反馈

- ChatBubble 尾部加 👍 👎 按钮
- 存入 `MessageFeedback` 表（messageId + userId + rating + comment）
- 定期离线分析：低分消息的共性 → 优化 prompt

---

### 2.4 CI/CD

**现状**：手动 `npm run dev` + `git push`。

**方案**：

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  test-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd trip-server && npm ci
      - run: cd trip-server && npx tsc --noEmit
      - run: cd trip-server && npx vitest run
  test-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
      - run: cd trip-front && npm ci
      - run: cd trip-front && npx vue-tsc --noEmit
      - run: cd trip-front && npx vitest run
```

pre-commit hooks（`husky` + `lint-staged`）：
```json
{
  "husky": {
    "hooks": {
      "pre-commit": "lint-staged"
    }
  },
  "lint-staged": {
    "*.ts": ["eslint --fix", "prettier --write"],
    "*.vue": ["eslint --fix", "prettier --write"]
  }
}
```

---

### 2.5 安全加固

**当前风险**：
- SQL 注入：`knowledgeService.mysqlKeywordSearch` 用了 `prisma.$queryRawUnsafe` 直接拼接 SQL
- 无 CSRF 保护
- 无请求体大小限制
- 错误响应暴露 `e.message` 可能泄漏内部信息

**改进**：

| 风险 | 修复 |
|---|---|
| SQL 注入 | `mysqlKeywordSearch` 改用 `prisma.$queryRaw` 参数化查询或 `prisma.spot.findMany({ where: { OR: [...] } })` |
| CSRF | `csurf` 中间件或 SameSite Cookie |
| Body 限制 | `express.json({ limit: '1mb' })` |
| 错误信息泄漏 | 生产环境 `NODE_ENV=production` 时返回通用错误，详细错误仅写日志 |
| 速率限制 | 除 chat 外的接口也加上限流（recommend 5/min，knowledge CRUD 10/min） |

---

### 2.6 缓存策略

**现状**：每次请求都重新计算 embedding + 搜索 Chroma + rerank。

**方案**：

```
┌─ query "成都必去景点" ──────────────────┐
│                                         │
│  1. 计算 query embedding               │
│  2. Redis: GET embed:md5(query)        │
│     ├─ HIT → 跳过 embedding 计算       │
│     └─ MISS → 计算 → SET with TTL 1h  │
│  3. Redis: GET search:city:"成都":md5  │
│     ├─ HIT → 直接返回结果              │
│     └─ MISS → 执行三路召回 → SET 1h   │
│  4. 返回结果                           │
└─────────────────────────────────────────┘
```

- **Query Embedding 缓存**：MD5 hash 做 key，TTL 1 小时
- **搜索结果缓存**：`{city}:{category?}:{queryHash}` → 结果 JSON，TTL 根据城市热门程度差异化
- **天气缓存**：`weather:{city}` → TTL 30 分钟

---

## 三、架构层面

### 3.1 LangGraph 替代 AgentExecutor

**现状问题**：

AgentExecutor 是一个隐式的 while 循环——你不知道 Agent 会在第几轮停止，也无法精确控制工具调用顺序。面试官常见的追问：

> "如果你想强制 Agent 先查天气再查距离最后做规划，AgentExecutor 能做到吗？"

**LangGraph 方案**：

把 Agent 流程建模为有向状态图：

```typescript
import { StateGraph, END } from '@langchain/langgraph'

interface AgentState {
  messages: BaseMessage[]
  next: string        // 下一个节点
  toolCalls: number    // 已经调了多少次工具
}

const graph = new StateGraph<AgentState>({
  channels: {
    messages: { value: (a, b) => a.concat(b), default: () => [] },
    next: { value: (_, b) => b, default: () => 'agent' },
    toolCalls: { value: (_, b) => b, default: () => 0 },
  },
})

// 节点定义
graph.addNode('agent', async (state) => {
  const response = await llm.invoke(state.messages)
  return { messages: [response], next: hasToolCalls(response) ? 'tools' : 'answer' }
})

graph.addNode('tools', async (state) => {
  const lastMsg = state.messages[state.messages.length - 1]
  const results = await executeTools(lastMsg.tool_calls)
  return { messages: results, next: 'agent', toolCalls: state.toolCalls + 1 }
})

graph.addNode('answer', async (state) => {
  return { messages: [], next: END }
})

// 条件边：超 N 次工具调用则强制结束
graph.addConditionalEdges('agent', (state) => state.next)
graph.addConditionalEdges('tools', (state) => {
  return state.toolCalls >= 5 ? 'answer' : 'agent'
})

graph.setEntryPoint('agent')
```

**优势**：
- 可精确控制执行路径（条件边）
- 可注入安全检查节点（过滤工具输出）
- 支持并行工具调用（`send()` 多路）
- 天然支持流式（`stream()` 方法按节点发射事件）

---

### 3.2 多 Agent 协作

**现状问题**：单一 Agent 承担所有职责（检索 + 规划 + 输出），随着工具增多，性能下降、输出不稳定。

**方案**：

```
┌─ Orchestrator Agent (协调器) ──────────────┐
│  "规划北京三日游" → 拆解任务:               │
│    1. 检索北京景点信息 → Research Agent     │
│    2. 生成行程规划 → Planner Agent          │
│    3. 交叉验证 → Verifier Agent             │
└──────────┬───────────┬───────────┬─────────┘
           ↓           ↓           ↓
   ┌─ Research ─┐ ┌─ Planner ─┐ ┌─ Verifier ─┐
   │ 调用 RAG    │ │ 调用距离  │ │ 检查天数   │
   │ 调用天气    │ │ 调用酒店  │ │ 检查预算   │
   │ 返回 5 景点 │ │ 生成 JSON │ │ 返回报告   │
   └─────────────┘ └───────────┘ └────────────┘
```

**技术选型**：
- **CrewAI**：Python 生态，成熟的角色分工框架
- **LangGraph 多 Agent**：通过子图 (subgraph) 实现，与前文 LangGraph 方案一致推荐
- **手动编排**：用 `DynamicStructuredTool` 将其他 Agent 包装为 Tool，由主 Agent 调用

```
Orchestrator.tools = [
  researchTool,    // → 调用 Research Agent
  plannerTool,     // → 调用 Planner Agent
  verifierTool,    // → 调用 Verifier Agent
]
```

---

### 3.3 语义缓存

**现状问题**："成都三日游"和"成都三天行程推荐"语义相同，但每次都重新跑 embedding + 检索 + LLM 生成。

**方案**：

```typescript
import Redis from 'ioredis'
const redis = new Redis()

const SEMANTIC_THRESHOLD = 0.92  // 余弦相似度阈值

export async function semanticCache(query: string): Promise<string | null> {
  // 1. 计算 query embedding
  const embedding = await embedText(query)

  // 2. Redis 缓存模式：存储 query → { embedding, response }
  const cached = await redis.get(`llm:${md5(query)}`)
  if (cached) return JSON.parse(cached).response

  // 3. 从 Chroma 向量存储中查相似 query
  const results = await queryCacheCollection.query({
    queryEmbeddings: [embedding],
    nResults: 1,
  })

  if (results.distances?.[0]?.[0] < (1 - SEMANTIC_THRESHOLD)) {
    return results.documents?.[0]?.[0] ?? null
  }

  return null  // 未命中
}

export async function cacheResponse(query: string, response: string) {
  const embedding = await embedText(query)
  await queryCacheCollection.add({
    ids: [randomUUID()],
    embeddings: [embedding],
    documents: [response],
    metadatas: [{ query, timestamp: Date.now() }],
  })
}
```

**缓存粒度**：

| 缓存层级 | 数据类型 | TTL | 存储 |
|---|---|---|---|
| L1: 查询改写缓存 | `query → rewrittenQuery` | 24h | Redis |
| L2: Query Embedding | `query → embedding` | 1h | Redis + LRU |
| L3: 搜索结果缓存 | `city:query → spots[]` | 1h | Redis |
| L4: Agent 回复缓存 | `query → fullResponse` | 30min | Chroma（语义检索） |

---

### 3.4 流式方案升级

**现状问题**：
- 用 `streamEnabled` 布尔开关过滤 Agent 中间输出，是事后打补丁式的方案
- 前端没有背压机制，大量 SSE 数据积压时体验差
- 不支持流式中断后恢复

**方案**：

#### 3.4.1 LangGraph Streaming

```typescript
// LangGraph 的 stream() 方法按节点发射事件
for await (const event of graph.stream({ messages: [userMsg] }, {
  streamMode: 'updates',  // 或 'messages' / 'values'
  subgraphs: true,
})) {
  // 精确知道当前在哪个节点
  if (event.node === 'research_agent') {
    onEvent({ type: 'tool_start', name: 'research' })
  } else if (event.node === 'planner_agent') {
    if (event.event === 'on_chat_model_stream') {
      onEvent({ type: 'chunk', content: token })
    }
  }
}
```

#### 3.4.2 背压（Backpressure）

```typescript
// 读取 ReadableStream 时手动控制流速
const reader = response.body!.getReader()
let pending = 0
const MAX_PENDING = 100

while (true) {
  if (pending >= MAX_PENDING) {
    // 等待前端消费
    await new Promise(r => setTimeout(r, 50))
  }
  const { done, value } = await reader.read()
  if (done) break
  pending++
  processChunk(value, () => pending--)
}
```

#### 3.4.3 流式中断恢复

- 客户端 `AbortController.abort()` 后，后端检测 `res.writableEnded`
- 已生成的部分回复持久化（`persistAssistant` 已支持）
- 前端下次进入对话时，对比本地 `localStorage` 中保存的 `conversationId` + `lastMessageId`，请求 `GET /api/conversations/:id/messages?since=CUTOFF_ID` 增量加载

---

### 3.5 混合检索升级

**现状**：三路召回（Chroma 向量 + MySQL LIKE + MySQL Rating），但 LIKE 搜索精度差。

**方案**：引入 BM25 关键词检索（Elasticsearch / Meilisearch）。

```
三路召回 + RRF 融合
├── 语义检索: Chroma (bge-small-zh, 512维, cosine) → top-20
├── 关键词检索: Elasticsearch BM25 → top-10
├── 排序检索: MySQL rating DESC → top-10
│
└── RRF 融合 (K=60)
    └── Cross-Encoder Reranker (bge-reranker-base)
        └── top-5
```

**为什么 BM25 优于 LIKE**：
- LIKE `%keyword%` 无法处理同义词（"便宜" ≠ "实惠"）
- BM25 有 TF-IDF 权重，高频词得分低，低频词得分高
- Elasticsearch 自带中文分词（`ik_max_word` / `ik_smart`）

**轻量替代**：Meilisearch（Rust 实现，10MB 内存即可运行，自带中文分词）。

**新增配置**：
```typescript
const searchClient = new MeiliSearch({ host: 'http://localhost:7700' })
const index = searchClient.index('spots')

await index.updateFilterableAttributes(['city', 'category'])
await index.updateSearchableAttributes(['name', 'description', 'tags'])
```

---

### 3.6 Agent 即服务

**现状**：Agent 与 Express 进程强耦合。Agent 崩溃 = 整个 API 崩溃。

**方案**：将 Agent 拆成独立服务，通过消息队列通信。

```
┌─ API Server (Express) ────┐
│  接收请求                    │
│  路由/鉴权/会话管理          │
│  通过消息队列入队任务         │
└────────┬───────────────────┘
         │ Redis / BullMQ
         ↓
┌─ Agent Worker ─────────────┐
│  worker-1: 处理 chat 任务   │
│  worker-2: 处理 recommend   │
│  worker-3: 处理 optimize    │
│  可独立扩缩容                │
│  崩溃不影响 API              │
└─────────────────────────────┘
```

**BullMQ 示例**：
```typescript
import { Queue, Worker } from 'bullmq'

const chatQueue = new Queue('chat', { connection: redis })
const chatWorker = new Worker('chat', async (job) => {
  const { userId, message, conversationId } = job.data
  const result = await agentEngine.chat({
    userId, message, conversationId,
    onEvent: async (event) => {
      // 通过 WebSocket 推送给前端
      wsServer.emit(job.data.socketId, event)
    },
  })
  return result
}, { connection: redis })

// API 端
app.post('/api/trip/chat', async (req, res) => {
  const job = await chatQueue.add('chat-message', {
    userId: req.user.userId,
    message: req.body.message,
    socketId: req.headers['x-socket-id'],
  })
  res.json({ jobId: job.id, status: 'queued' })
})
```

**优势**：
- Agent 进程死掉不影响 API 接受请求
- 可独立监控 Agent 吞吐量、队列积压
- 未来可支持不同的 LLM 提供方策略（`providerFailover`）

---

## 实施优先级

按面试价值和技术深度排序：

| 优先级 | 改进项 | 为什么先做 |
|---|---|---|
| 🔴 P0 | 测试体系 | 面试第一问——"你怎么保证质量？" |
| 🔴 P0 | 可观测性 | 没有它，后续所有性能/稳定性工作无从下手 |
| 🟡 P1 | Agent 评估体系 | 从"能跑"到"跑得好"的标志 |
| 🟡 P1 | LangGraph 重构 | 架构面试的核心——"你为什么不继续用 LangChain？" |
| 🟡 P1 | 语义缓存 | 性能优化经典话题，RAG 场景完美适配 |
| 🟢 P2 | 多 Agent 协作 | 系统设计面试必问——"你项目里的并发/分布式怎么做的？" |
| 🟢 P2 | CI/CD | 基础工程素养 |
| 🟢 P2 | 安全加固 | 安全红线意识 |
| 🔵 P3 | 行程导出 | 产品完整性 |
| 🔵 P3 | 多模态识别 | AI 广度 |
| 🔵 P3 | 行程协作 | 实时通信场景 |
| ⚪ P4 | Agent 即服务 | 架构升级 |
| ⚪ P4 | 混合检索升级 | 搜索引擎深度 |
| ⚪ P4 | 推送通知 | 可用性加分 |
| ⚪ P4 | PWA | 移动端体验 |
