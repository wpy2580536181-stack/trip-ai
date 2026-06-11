# AI Agent + RAG 智能旅行系统升级设计

> 2026-06-11 · 项目：Trip — AI 智能旅行规划系统

## 1. 概述

将现有基础的 AI 旅行规划系统升级为完整的 RAG + Agent 架构，解决 LLM 幻觉、无对话记忆、行程不持久化等核心问题，并引入 Tool Calling 实现智能旅行助手。

**目标**：
- 提升 AI 规划质量（基于真实景点数据 + 对话上下文）
- 增强用户体验（对话记忆、行程持久化、个性化推荐）
- 技术栈升级（覆盖 RAG、Agent、Tool Calling、Structured Output）

## 2. 架构

### 2.1 整体架构

```
用户请求
  │
  ▼
┌──────────────────────────────────────┐
│           Express API 层              │
│  /api/trip/*  /api/knowledge/*       │
│  /api/history/*                      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│        Agent Engine (编排层)          │
│  ┌─────────┐ ┌────────┐ ┌────────┐  │
│  │ Memory  │ │  RAG   │ │ Tool   │  │
│  │ Manager │ │  Tool  │ │Registry│  │
│  └────┬────┘ └───┬────┘ └───┬────┘  │
│       │          │          │       │
│       ▼          ▼          ▼       │
│  ┌────────┐ ┌────────┐ ┌────────┐   │
│  │ MySQL  │ │ Chroma │ │External│   │
│  │对话/   │ │向量检索 │ │APIs    │   │
│  │行程    │ │        │ │(带容错)│   │
│  └────────┘ └────────┘ └────────┘   │
└──────────────────────────────────────┘
```

### 2.2 核心设计决策

1. **Agent Engine = 编排层**：内部持有 Memory Manager、RAG Tool、Tool Registry，Express 路由只和 Agent Engine 交互
2. **RAG 作为 Agent Tool**：`retrieve_knowledge` 工具注册到 Agent，Agent 自主决定何时查知识库
3. **Tool 容错层**：所有外部 API Tool 统一封装超时(5s)、重试(2次)、降级(友好提示)、调用日志

### 2.3 新增模块

| 模块 | 职责 |
|---|---|
| Agent Engine | 统一编排层，管理 Agent 生命周期 |
| Memory Manager | 对话历史持久化 + 滑动窗口(10轮) + 摘要压缩 |
| RAG Pipeline | 知识库检索 → 上下文注入（封装为 Tool） |
| Tool Registry | 注册和管理所有 Agent 可用工具 |
| Resilience Layer | Tool 超时/重试/降级/日志 |

## 3. 技术选型

| 组件 | 选型 | 理由 |
|---|---|---|
| 向量数据库 | Chroma | 本地运行、免费、LangChain 集成好 |
| Embedding 模型 | bge-small-zh | 中文效果好、免费、本地运行 |
| Agent 框架 | LangChain createReactAgent | 已有 LangChain 依赖，ReAct 模式成熟 |
| 结构化输出 | 自定义解析 + Zod 校验 | 替代正则 JSON 解析 |

### 3.1 新增依赖

```json
{
  "chromadb": "^1.x",
  "@langchain/community": "^0.x",
  "@xenova/transformers": "^2.x",
  "zod": "^3.x"
}
```

## 4. 数据模型

### 4.1 新增 Prisma 表

```prisma
model Trip {
  id              Int      @id @default(autoincrement())
  user_id         Int
  city            String   @db.VarChar(50)
  days            Int
  budget          Int
  content         Json
  status          String   @default("completed") @db.VarChar(20)
  parent_trip_id  Int?
  created_at      DateTime @default(now())
  user            User     @relation(fields: [user_id], references: [id])
  parent          Trip?    @relation("TripVersions", fields: [parent_trip_id], references: [id])
  versions        Trip[]   @relation("TripVersions")

  @@index([user_id])
}

model Conversation {
  id          Int       @id @default(autoincrement())
  user_id     Int
  title       String?   @db.VarChar(100)
  summary     String?   @db.Text
  created_at  DateTime  @default(now())
  updated_at  DateTime  @updatedAt
  user        User      @relation(fields: [user_id], references: [id])
  messages    Message[]

  @@index([user_id])
}

model Message {
  id              Int          @id @default(autoincrement())
  conversation_id Int
  role            String       @db.VarChar(20)
  content         String       @db.Text
  metadata        Json?
  created_at      DateTime     @default(now())
  conversation    Conversation @relation(fields: [conversation_id], references: [id], onDelete: Cascade)

  @@index([conversation_id, created_at])
}

model Spot {
  id          Int      @id @default(autoincrement())
  name        String   @db.VarChar(100)
  city        String   @db.VarChar(50)
  category    String   @db.VarChar(20)
  description String   @db.Text
  tags        Json
  avg_cost    Float?
  duration    String?  @db.VarChar(50)
  open_time   String?  @db.VarChar(100)
  rating      Float?
  vector_id   String?  @db.VarChar(100)
  created_at  DateTime @default(now())
  updated_at  DateTime @updatedAt

  @@index([city, category])
  @@unique([vector_id])
}
```

### 4.2 User 模型扩展

```prisma
model User {
  // ... 现有字段
  trips          Trip[]
  conversations  Conversation[]
  preferences    Json?    // 旅行偏好：{ style: "adventure", budget_level: "medium" }
}
```

## 5. RAG 知识库

### 5.1 文档结构

```typescript
interface SpotDocument {
  id: string;
  content: string;  // 景点描述文本（用于 embedding）
  metadata: {
    city: string;
    name: string;
    category: 'attraction' | 'food' | 'hotel' | 'transport';
    tags: string[];
    avgCost?: number;
    duration?: string;
    openTime?: string;
    rating?: number;
  };
}
```

### 5.2 检索流程

1. Agent 决定调用 `retrieve_knowledge` 工具
2. 工具接收 query、city、category 参数
3. Chroma 执行相似度搜索（top-5），按 city 过滤
4. 返回匹配的景点信息文本

### 5.3 数据管理

- 初始数据：JSON 文件（`trip-server/data/spots/*.json`），通过 seed 脚本导入 MySQL + Chroma
- 管理接口（ADMIN 权限）：CRUD `/api/knowledge/spots`
- 数据同步：MySQL 为权威源，更新时同步 Chroma 向量（事务性同步，失败回滚）

### 5.4 Embedding

- 模型：`bge-small-zh`（通过 `@xenova/transformers` 本地运行）
- 维度：512
- 中文优化，无需 API Key

## 6. Agent Engine

### 6.1 Agent 工具列表

| 工具名 | 类型 | 说明 |
|---|---|---|
| `retrieve_knowledge` | RAG | 检索景点知识库 |
| `get_weather` | 外部 API | 查询目的地天气（Phase 2） |
| `calculate_distance` | 外部 API | 计算景点间距离/交通时间（Phase 2） |
| `save_trip` | 内部 | 保存行程到数据库 |

**注**：用户偏好不作为工具，改为在 Agent 初始化时直接注入 System Prompt。

### 6.2 Memory Manager 策略

Agent 收到的完整上下文：
- **SystemMessage** = [系统角色] + [用户偏好（直接注入）] + [历史摘要（>10轮前的消息压缩）]
- **Messages** = [最近 10 轮原始消息（user/assistant 交替）]

具体流程：
1. 对话开始时，查询该会话的消息总数
2. 若 ≤ 10 轮：直接加载全部原始消息
3. 若 > 10 轮：
   - 取第 11 轮及之前的消息 → 检查 `Conversation.summary` 字段
   - 无摘要 → 调用 LLM 压缩为一段摘要文本 → 缓存到 `Conversation.summary`
   - 有摘要 → 直接用缓存摘要 + 增量压缩新溢出窗口外的消息
4. 组装：`[SystemMessage(角色+偏好+摘要), ...最近10轮原始消息]`

### 6.3 Agent 结构化输出策略

**问题**：`withStructuredOutput` 与 ReAct Agent 多步推理不兼容。

**解决方案**：Agent 最终输出不做 Schema 约束，而是在 Agent 完成后做后处理：

```typescript
async recommend(userId, city, budget, days) {
  // 1. Agent 自由推理 + 工具调用
  const result = await agent.invoke({ messages });
  
  // 2. 从最终消息中提取结构化数据
  const finalMessage = result.messages[result.messages.length - 1];
  const parsed = TripSchema.safeParse(JSON.parse(extractJson(finalMessage.content)));
  
  // 3. Schema 校验失败 → 重试一次（附带上错误信息）
  if (!parsed.success) {
    const retry = await agent.invoke({
      messages: [...result.messages, new SystemMessage(`输出格式错误: ${parsed.error.message}，请重新输出`)]
    });
    // 再次解析...
  }
  
  return parsed.data;
}
```

**System Prompt 强调**：
> "完成所有工具调用后，你的最终回复必须是严格的 JSON 格式，包含以下字段：..."

### 6.4 容错降级策略

| 场景 | 降级行为 |
|---|---|
| Chroma 未启动 | `retrieve_knowledge` 返回 "知识库暂不可用"，Agent 退化为纯 LLM 模式 |
| 外部 API 超时/失败 | 返回 "数据暂时无法获取"，Agent 继续规划但不含该项建议 |
| `save_trip` 数据库失败 | Agent 感知错误，告知用户"行程已生成但保存失败，请重试"，同时返回行程内容 |
| Embedding 模型加载失败 | 启动时检测，失败则 RAG 功能禁用并记录告警 |

### 6.5 容错封装

```typescript
interface ResilienceConfig {
  timeout: number;      // 默认 5000ms
  retries: number;      // 默认 2
  fallback: string;     // 降级提示
}

function withResilience(tool: DynamicStructuredTool, config?: ResilienceConfig): DynamicStructuredTool
```

## 7. MySQL-Chroma 同步策略

采用**同步写入 + 失败回滚**：

```typescript
async createSpot(data: CreateSpotInput) {
  // 1. 生成 embedding
  const embedding = await embedDocument(data.description);
  
  // 2. 写 MySQL
  const spot = await prisma.spot.create({ data: { ...data, vector_id: uuid() } });
  
  try {
    // 3. 同步写 Chroma
    await chromaCollection.add({
      ids: [spot.vector_id!],
      embeddings: [embedding],
      documents: [data.description],
      metadatas: [{ city: data.city, name: data.name, category: data.category }],
    });
  } catch (e) {
    // 4. Chroma 失败 → 回滚 MySQL + 记录日志
    await prisma.spot.delete({ where: { id: spot.id } });
    logger.error(`Chroma sync failed for spot ${spot.id}: ${e.message}`);
    throw new Error('知识库同步失败，请稍后重试');
  }
  
  return spot;
}
```

## 8. API 变更

### 8.1 改造的接口

| 接口 | 变更 |
|---|---|
| `POST /api/trip/recommend` | 改为走 Agent，自动 RAG + 保存行程，需认证 |
| `POST /api/trip/chat` | 改为走 Agent，支持多轮对话 + 对话会话 |

### 8.2 新增接口

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| POST | `/api/trip/conversations` | 新建对话会话 | 需认证 |
| GET | `/api/history/trips` | 历史行程列表 | 需认证 |
| GET | `/api/history/trips/:id` | 行程详情 | 需认证 |
| GET | `/api/history/conversations` | 对话列表 | 需认证 |
| GET | `/api/history/conversations/:id` | 对话详情 | 需认证 |
| DELETE | `/api/history/conversations/:id` | 删除对话 | 需认证 |
| POST | `/api/knowledge/import` | 批量导入景点 | ADMIN |
| POST | `/api/knowledge/spots` | 添加景点 | ADMIN |
| PUT | `/api/knowledge/spots/:id` | 更新景点 | ADMIN |
| DELETE | `/api/knowledge/spots/:id` | 删除景点 | ADMIN |
| GET | `/api/knowledge/spots` | 景点列表 | 需认证 |

## 9. 行程优化流程（Phase 2）

```
用户点击"AI 优化" → 前端传入 tripId + 修改意见
  │
  ▼
Agent 接收：
  - 加载原行程 JSON（通过 tripId）
  - 用户修改意见（如"第二天下午换个景点"）
  │
  ▼
Agent 调用 retrieve_knowledge 查找替代景点
  │
  ▼
生成新版行程 → save_trip（新建记录，关联 parent_trip_id）
  │
  ▼
前端展示新版本，保留"查看旧版"入口
```

Trip 表 `parent_trip_id` 字段形成版本链。

## 10. 前端变更

| 页面 | 变更 |
|---|---|
| Chat.vue | 支持对话会话管理（新建/切换/历史）；展示 Tool 调用状态 |
| Detail.vue | 行程持久化；从历史记录加载；"AI 优化"按钮（Phase 2） |
| 新增 History.vue | 历史行程列表，查看/删除 |
| Profile.vue | 旅行偏好设置（Phase 2） |

## 11. 实施阶段

### Phase 1 — 质量基础
- **Phase 1a**：chat 接口跑通 Agent + RAG + Memory（单会话）
- **Phase 1b**：recommend 接口复用 Agent 子流程
- **Phase 1c**：前端单会话 UI + 历史行程页
- **Phase 1.5**：多会话侧边栏

### Phase 2 — Agent 能力扩展
1. 外部 API Tools（天气、距离、酒店）
2. 行程优化功能
3. 用户偏好系统
4. 前端 Tool 调用状态展示

### Phase 3 — 知识库管理
1. 知识库 CRUD API
2. 知识库管理前端
3. 景点数据扩充

## 12. 后续规划

Phase 1 完成后，使用 writing-plans skill 制定 Phase 1a 的详细实施计划。
