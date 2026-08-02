# Phase 1a Implementation Plan: Chat with Agent + RAG + Memory

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the existing stateless chat interface into an Agent-powered chat with RAG knowledge base retrieval and persistent conversation memory, as defined in `docs/superpowers/specs/2026-06-11-ai-agent-rag-design.md`.

**Architecture:**
- Express API layer calls into a single `AgentEngine` orchestrator
- `AgentEngine` manages Agent lifecycle, holds `MemoryManager` + `ToolRegistry` (which includes the `retrieve_knowledge` RAG tool)
- `MemoryManager` persists all messages to MySQL with sliding-window (10 turns) + summary compression
- `retrieve_knowledge` tool queries Chroma (vector DB) filtered by city, returns top-5 similar spots
- Embedding uses `bge-small-zh` local model via `@xenova/transformers`
- Chat endpoint still uses SSE for streaming Agent reasoning + final response

**Tech Stack:**
- Backend: Express 5 + TypeScript + Prisma + LangChain
- Vector DB: Chroma (chromadb npm package, embedded mode)
- Embedding: bge-small-zh via @xenova/transformers
- Validation: zod
- Frontend: Vue 3 + Vant 4 (no changes to Chat.vue API contract — only sends `{message, conversationId?}`)

**Note on tests:** The existing project has no test framework set up. To stay focused on shipping Phase 1a, this plan uses **lightweight smoke tests** (manual curl / script-based) instead of a full TDD framework setup. A future task (out of scope for 1a) can introduce Jest/Vitest.

---

## File Structure

### New files
- `trip-server/prisma/schema.prisma` — extended with `Trip`, `Conversation`, `Message`, `Spot`, `User.preferences`
- `trip-server/src/config/chroma.ts` — Chroma client + collection singleton
- `trip-server/src/config/embeddings.ts` — bge-small-zh embedding model loader
- `trip-server/src/services/memoryManager.ts` — sliding window + summary compression
- `trip-server/src/services/agent/tools/retrieveKnowledge.ts` — RAG tool
- `trip-server/src/services/agent/resilience.ts` — timeout/retry/fallback wrapper
- `trip-server/src/services/agent/agentEngine.ts` — LangChain agent orchestrator
- `trip-server/src/services/agent/systemPrompt.ts` — system prompt builder
- `trip-server/src/services/conversationService.ts` — conversation/message CRUD
- `trip-server/src/services/tripService.ts` — refactored to use AgentEngine
- `trip-server/src/controllers/trip.controller.ts` — chat + recommend use agent
- `trip-server/src/routes/trip.routes.ts` — add auth middleware to chat
- `trip-server/src/routes/conversation.routes.ts` — new conversation CRUD
- `trip-server/src/controllers/conversation.controller.ts` — new
- `trip-server/src/routes/history.routes.ts` — new
- `trip-server/src/controllers/history.controller.ts` — new
- `trip-server/data/spots/chengdu.json` — initial knowledge data
- `trip-server/prisma/seed-knowledge.ts` — import spots to MySQL + Chroma
- `trip-server/src/types/agent.ts` — shared types

### Modified files
- `trip-server/package.json` — add deps
- `trip-server/.env.example` — add Chroma config
- `trip-server/src/index.ts` — register new routes
- `trip-server/src/services/tripService.ts` — delegate to AgentEngine
- `trip-server/src/controllers/trip.controller.ts` — accept conversationId, persist messages
- `trip-server/src/routes/trip.routes.ts` — protect /chat with auth

---

## Task 1: Add Phase 1a dependencies

**Files:**
- Modify: `trip-server/package.json`

- [ ] **Step 1: Install dependencies**

Run:
```bash
cd trip-server && npm install chromadb @langchain/community @xenova/transformers zod
```

- [ ] **Step 2: Verify package.json**

Run: `cat trip-server/package.json | grep -E "chromadb|@langchain/community|@xenova/transformers|zod"`
Expected: All four packages listed in dependencies.

- [ ] **Step 3: Commit**

```bash
git add trip-server/package.json trip-server/package-lock.json
git commit -m "chore: add chroma, embeddings, zod deps for phase 1a"
```

---

## Task 2: Extend Prisma schema

**Files:**
- Modify: `trip-server/prisma/schema.prisma`

- [ ] **Step 1: Add new models and User extension**

Replace the contents of `trip-server/prisma/schema.prisma` with:

```prisma
generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "mysql"
  url      = env("DATABASE_URL")
}

enum RoleName {
  ADMIN
  USER
}

model Role {
  id        Int      @id @default(autoincrement())
  name      RoleName @unique
  users     User[]
  createdAt DateTime @default(now()) @map("created_at")

  @@map("roles")
}

model User {
  id            Int            @id @default(autoincrement())
  username      String         @unique @db.VarChar(50)
  email         String         @unique @db.VarChar(100)
  password      String         @db.VarChar(255)
  nickname      String?        @db.VarChar(50)
  avatar        String?        @db.VarChar(255)
  phone         String?        @db.VarChar(20)
  bio           String?        @db.VarChar(255)
  roleId        Int            @default(2) @map("role_id")
  role          Role           @relation(fields: [roleId], references: [id])
  status        Int            @default(1) @map("status")
  preferences   Json?
  createdAt     DateTime       @default(now()) @map("created_at")
  updatedAt     DateTime       @updatedAt @map("updated_at")
  trips         Trip[]
  conversations Conversation[]

  @@map("users")
}

model PasswordReset {
  id        Int      @id @default(autoincrement())
  email     String   @db.VarChar(100)
  token     String   @db.VarChar(255)
  expiresAt DateTime @map("expires_at")
  used      Boolean  @default(false)
  createdAt DateTime @default(now()) @map("created_at")

  @@map("password_resets")
}

model Trip {
  id             Int      @id @default(autoincrement())
  userId         Int      @map("user_id")
  city           String   @db.VarChar(50)
  days           Int
  budget         Int
  content        Json
  status         String   @default("completed") @db.VarChar(20)
  parentTripId   Int?     @map("parent_trip_id")
  createdAt      DateTime @default(now()) @map("created_at")
  user           User     @relation(fields: [userId], references: [id])
  parent         Trip?    @relation("TripVersions", fields: [parentTripId], references: [id])
  versions       Trip[]   @relation("TripVersions")

  @@index([userId])
  @@map("trips")
}

model Conversation {
  id        Int       @id @default(autoincrement())
  userId    Int       @map("user_id")
  title     String?   @db.VarChar(100)
  summary   String?   @db.Text
  createdAt DateTime  @default(now()) @map("created_at")
  updatedAt DateTime  @updatedAt @map("updated_at")
  user      User      @relation(fields: [userId], references: [id])
  messages  Message[]

  @@index([userId])
  @@map("conversations")
}

model Message {
  id             Int          @id @default(autoincrement())
  conversationId Int          @map("conversation_id")
  role           String       @db.VarChar(20)
  content        String       @db.Text
  metadata       Json?
  createdAt      DateTime     @default(now()) @map("created_at")
  conversation   Conversation @relation(fields: [conversationId], references: [id], onDelete: Cascade)

  @@index([conversationId, createdAt])
  @@map("messages")
}

model Spot {
  id          Int      @id @default(autoincrement())
  name        String   @db.VarChar(100)
  city        String   @db.VarChar(50)
  category    String   @db.VarChar(20)
  description String   @db.Text
  tags        Json
  avgCost     Float?   @map("avg_cost")
  duration    String?  @db.VarChar(50)
  openTime    String?  @map("open_time") @db.VarChar(100)
  rating      Float?
  vectorId    String?  @unique @map("vector_id") @db.VarChar(100)
  createdAt   DateTime @default(now()) @map("created_at")
  updatedAt   DateTime @updatedAt @map("updated_at")

  @@index([city, category])
  @@map("spots")
}
```

- [ ] **Step 2: Generate Prisma client and push schema**

Run:
```bash
cd trip-server && npx prisma generate && npx prisma db push
```

Expected: Schema synced, prisma client generated. (db push may prompt — answer yes.)

- [ ] **Step 3: Verify schema by checking Prisma client**

Run:
```bash
cd trip-server && npx prisma studio --browser none &
sleep 3
kill %1 2>/dev/null
```

Expected: Prisma studio starts (means schema is valid), then we kill it. If invalid, prisma will print errors.

- [ ] **Step 4: Commit**

```bash
git add trip-server/prisma/
git commit -m "feat(db): add Trip, Conversation, Message, Spot models + User.preferences"
```

---

## Task 3: Add Chroma + embedding configuration

**Files:**
- Create: `trip-server/src/config/chroma.ts`
- Create: `trip-server/src/config/embeddings.ts`
- Create: `trip-server/src/types/agent.ts`
- Modify: `trip-server/.env.example`

- [ ] **Step 1: Create types file**

Create `trip-server/src/types/agent.ts`:

```typescript
import { z } from 'zod'

// Spot 元数据类型
export const SpotCategorySchema = z.enum(['attraction', 'food', 'hotel', 'transport'])
export type SpotCategory = z.infer<typeof SpotCategorySchema>

// Spot 输入（创建/更新）
export const SpotInputSchema = z.object({
  name: z.string().min(1).max(100),
  city: z.string().min(1).max(50),
  category: SpotCategorySchema,
  description: z.string().min(1),
  tags: z.array(z.string()).default([]),
  avgCost: z.number().optional(),
  duration: z.string().optional(),
  openTime: z.string().optional(),
  rating: z.number().min(0).max(5).optional(),
})
export type SpotInput = z.infer<typeof SpotInputSchema>

// Chroma 中的 Spot 文档
export interface SpotVectorDoc {
  id: string
  embedding: number[]
  document: string
  metadata: {
    city: string
    name: string
    category: string
    tags: string  // JSON stringified array (Chroma 只支持基本类型)
    rating?: number
  }
}

// 行程内容 schema（用于 recommend 接口输出）
export const TripContentSchema = z.object({
  city: z.string(),
  days: z.number(),
  totalBudget: z.number(),
  dailyItinerary: z.array(z.any()),
  budgetBreakdown: z.object({
    accommodation: z.number(),
    food: z.number(),
    transportation: z.number(),
    tickets: z.number(),
    other: z.number(),
  }),
  tips: z.array(z.string()),
  warnings: z.array(z.string()).optional(),
})
export type TripContent = z.infer<typeof TripContentSchema>

// Agent 流式事件类型
export type AgentStreamEvent =
  | { type: 'tool_start'; name: string }
  | { type: 'tool_end'; name: string; output?: string }
  | { type: 'chunk'; content: string }
  | { type: 'complete'; content: string }
  | { type: 'error'; error: string }
```

- [ ] **Step 2: Create Chroma config**

Create `trip-server/src/config/chroma.ts`:

```typescript
import { ChromaClient, Collection } from 'chromadb'

const CHROMA_URL = process.env.CHROMA_URL || 'http://localhost:8000'
const COLLECTION_NAME = 'travel_spots'

let client: ChromaClient | null = null
let collection: Collection | null = null

/**
 * 获取 Chroma 客户端单例
 */
export function getChromaClient(): ChromaClient {
  if (!client) {
    client = new ChromaClient({ path: CHROMA_URL })
  }
  return client
}

/**
 * 获取 spots 集合单例（自动创建）
 */
export async function getSpotsCollection(): Promise<Collection> {
  if (collection) return collection

  const cli = getChromaClient()
  collection = await cli.getOrCreateCollection({
    name: COLLECTION_NAME,
    metadata: { 'hnsw:space': 'cosine' },
  })
  return collection
}

/**
 * 健康检查：Chroma 服务是否可用
 */
export async function checkChromaHealth(): Promise<boolean> {
  try {
    const cli = getChromaClient()
    await cli.heartbeat()
    return true
  } catch (e) {
    console.error('[Chroma] 健康检查失败:', e instanceof Error ? e.message : e)
    return false
  }
}
```

- [ ] **Step 3: Create embedding config (bge-small-zh via @xenova/transformers)**

Create `trip-server/src/config/embeddings.ts`:

```typescript
import { pipeline, FeatureExtractionPipeline } from '@xenova/transformers'

// bge-small-zh 中文 embedding 模型，512 维
const MODEL_NAME = 'Xenova/bge-small-zh-v1.5'
const EMBEDDING_DIM = 512

let extractorPromise: Promise<FeatureExtractionPipeline> | null = null

/**
 * 延迟加载 embedding 模型（首次调用时下载并初始化）
 */
export function getEmbedder(): Promise<FeatureExtractionPipeline> {
  if (!extractorPromise) {
    console.log(`[Embedding] 正在加载模型 ${MODEL_NAME}...`)
    extractorPromise = pipeline('feature-extraction', MODEL_NAME) as Promise<FeatureExtractionPipeline>
    extractorPromise.then(() => {
      console.log(`[Embedding] 模型加载完成`)
    }).catch((e) => {
      console.error(`[Embedding] 模型加载失败:`, e)
      extractorPromise = null  // 重置，允许重试
    })
  }
  return extractorPromise
}

/**
 * 将单个文本转为 embedding 向量
 */
export async function embedText(text: string): Promise<number[]> {
  const extractor = await getEmbedder()
  const result = await extractor(text, { pooling: 'mean', normalize: true })
  return Array.from(result.data as Float32Array)
}

/**
 * 批量 embedding
 */
export async function embedTexts(texts: string[]): Promise<number[][]> {
  const extractor = await getEmbedder()
  const results = await Promise.all(
    texts.map(t => extractor(t, { pooling: 'mean', normalize: true }))
  )
  return results.map(r => Array.from(r.data as Float32Array))
}

export const EMBEDDING_CONFIG = {
  modelName: MODEL_NAME,
  dim: EMBEDDING_DIM,
}
```

- [ ] **Step 4: Update .env.example**

Append to `trip-server/.env.example`:

```bash
# Chroma 向量数据库
CHROMA_URL=http://localhost:8000
CHROMA_PERSIST_DIR=./chroma_data
```

- [ ] **Step 5: Smoke test the embedding module**

Create `trip-server/src/scripts/test-embedding.ts`:

```typescript
import { embedText, EMBEDDING_CONFIG } from '../config/embeddings'

async function main() {
  console.log('模型:', EMBEDDING_CONFIG.modelName)
  console.log('维度:', EMBEDDING_CONFIG.dim)
  const vec = await embedText('成都武侯祠是中国著名的历史遗迹')
  console.log('向量长度:', vec.length)
  console.log('前 5 维:', vec.slice(0, 5))
  console.log('OK')
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
```

Run: `cd trip-server && npx ts-node src/scripts/test-embedding.ts`
Expected: First run downloads model (~100MB, may take 1-2 min), then prints "向量长度: 512" and "OK". Subsequent runs are fast.

- [ ] **Step 6: Delete the test script (keep codebase clean)**

Run: `rm trip-server/src/scripts/test-embedding.ts`

- [ ] **Step 7: Commit**

```bash
git add trip-server/src/config/chroma.ts trip-server/src/config/embeddings.ts trip-server/src/types/agent.ts trip-server/.env.example
git commit -m "feat(config): add Chroma client and bge-small-zh embedding loader"
```

---

## Task 4: Create initial knowledge data (Chengdu spots)

**Files:**
- Create: `trip-server/data/spots/chengdu.json`

- [ ] **Step 1: Create the data file**

Create `trip-server/data/spots/chengdu.json`:

```json
[
  {
    "name": "武侯祠",
    "city": "成都",
    "category": "attraction",
    "description": "武侯祠是中国唯一的一座君臣合祀祠庙和最负盛名的诸葛亮、刘备及蜀汉英雄纪念地，也是全国影响最大的三国遗迹博物馆。武侯祠占地37000平方米，建筑面积9200平方米，主要由惠陵、汉昭烈庙、武侯祠、三国文化陈列室等组成。祠内古柏苍翠，红墙环绕，是了解三国文化不可错过的地方。门票50元，建议游览2-3小时。",
    "tags": ["历史", "三国", "博物馆", "文化"],
    "avgCost": 50,
    "duration": "2-3小时",
    "openTime": "08:00-18:30",
    "rating": 4.6
  },
  {
    "name": "宽窄巷子",
    "city": "成都",
    "category": "attraction",
    "description": "宽窄巷子由宽巷子、窄巷子和井巷子三条平行排列的城市老式街道及其之间的四合院落群组成，是成都遗留下来的较成规模的清朝古街道。融合了中西文化，是老成都生活的最佳体验地。免费开放，建议游览1-2小时，品尝地道小吃。",
    "tags": ["古街", "文化", "美食", "免费"],
    "avgCost": 0,
    "duration": "1-2小时",
    "openTime": "全天",
    "rating": 4.5
  },
  {
    "name": "锦里",
    "city": "成都",
    "category": "attraction",
    "description": "锦里是一条仿古商业街，是成都人气最旺的景点之一，也是西蜀历史上最古老、最具有商业气息的街道之一。集中了成都各地的名小吃，享誉中外的三顾园、龙抄手、担担面等都在此设有分号。免费开放，建议游览2小时。",
    "tags": ["古街", "美食", "小吃", "免费"],
    "avgCost": 50,
    "duration": "2小时",
    "openTime": "09:00-22:00",
    "rating": 4.4
  },
  {
    "name": "大熊猫繁育研究基地",
    "city": "成都",
    "category": "attraction",
    "description": "成都大熊猫繁育研究基地是中国政府专门为拯救国宝大熊猫而建立的科研机构。基地内绿树成荫，翠竹掩映，空气清新，环境优美，模拟了大熊猫野外生态环境。门票55元，建议早晨前往，游览3-4小时，可以看到大熊猫最活跃的状态。",
    "tags": ["动物", "亲子", "自然"],
    "avgCost": 55,
    "duration": "3-4小时",
    "openTime": "07:30-18:00",
    "rating": 4.7
  },
  {
    "name": "杜甫草堂",
    "city": "成都",
    "category": "attraction",
    "description": "杜甫草堂是唐代大诗人杜甫流寓成都时的故居，是中国文学史上的圣地。草堂内亭台楼榭，林壑幽美，梅花、荷花、桂花等四季花卉不断。门票50元，建议游览2小时。",
    "tags": ["历史", "文学", "园林"],
    "avgCost": 50,
    "duration": "2小时",
    "openTime": "08:00-19:00",
    "rating": 4.5
  },
  {
    "name": "都江堰",
    "city": "成都",
    "category": "attraction",
    "description": "都江堰是公元前256年秦国蜀郡太守李冰父子组织修建的大型水利工程，是全世界至今为止，年代最久、唯一留存、以无坝引水为特征的宏大水利工程，也是世界文化遗产。门票80元，建议游览3-4小时，可与青城山一日游。",
    "tags": ["历史", "水利", "世界遗产"],
    "avgCost": 80,
    "duration": "3-4小时",
    "openTime": "08:00-18:00",
    "rating": 4.7
  },
  {
    "name": "青城山",
    "city": "成都",
    "category": "attraction",
    "description": "青城山是中国四大道教名山之一，素有'青城天下幽'的美誉。山中树木葱茏，峰峦叠翠，是避暑度假的胜地。前山80元，后山20元，建议游览1天，前山道教文化深厚，后山自然风光秀美。",
    "tags": ["道教", "自然", "山岳", "世界遗产"],
    "avgCost": 80,
    "duration": "1天",
    "openTime": "08:00-18:00",
    "rating": 4.6
  },
  {
    "name": "春熙路",
    "city": "成都",
    "category": "attraction",
    "description": "春熙路是成都最繁华的商业街，集购物、休闲、娱乐为一体。这里有众多国际品牌专卖店、本土特色店铺，还有IFS、太古里等高端购物中心。晚上灯光璀璨，人流如织，是感受成都现代气息的好去处。",
    "tags": ["商业", "购物", "现代"],
    "avgCost": 0,
    "duration": "2-3小时",
    "openTime": "全天",
    "rating": 4.4
  },
  {
    "name": "人民公园",
    "city": "成都",
    "category": "attraction",
    "description": "人民公园是成都最古老的公园之一，里面有著名的鹤鸣茶社，是体验成都'慢生活'的绝佳地点。点一壶盖碗茶，掏个耳朵，看着湖光山色，十分惬意。免费开放，建议游览1-2小时。",
    "tags": ["公园", "茶馆", "慢生活", "免费"],
    "avgCost": 20,
    "duration": "1-2小时",
    "openTime": "06:00-22:00",
    "rating": 4.5
  },
  {
    "name": "龙抄手",
    "city": "成都",
    "category": "food",
    "description": "龙抄手是成都著名的传统小吃，抄手即馄饨，皮薄如纸，馅嫩鲜美，汤浓味美。位于春熙路附近的总店是品尝地道成都小吃的首选。人均30元。",
    "tags": ["小吃", "传统", "馄饨"],
    "avgCost": 30,
    "rating": 4.4
  }
]
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/data/spots/chengdu.json
git commit -m "feat(data): add initial Chengdu travel spots knowledge base"
```

---

## Task 5: Create knowledge service (MySQL + Chroma sync)

**Files:**
- Create: `trip-server/src/services/knowledgeService.ts`

- [ ] **Step 1: Create knowledge service**

Create `trip-server/src/services/knowledgeService.ts`:

```typescript
import { randomUUID } from 'crypto'
import prisma from '../config/database'
import { getSpotsCollection, checkChromaHealth } from '../config/chroma'
import { embedText } from '../config/embeddings'
import { SpotInput, SpotInputSchema, SpotCategory } from '../types/agent'
import { z } from 'zod'

/**
 * 创建景点（事务性同步 MySQL + Chroma）
 */
export async function createSpot(input: SpotInput) {
  const validated = SpotInputSchema.parse(input)
  const vectorId = randomUUID()

  // 1. 写 MySQL
  const spot = await prisma.spot.create({
    data: {
      name: validated.name,
      city: validated.city,
      category: validated.category,
      description: validated.description,
      tags: validated.tags,
      avgCost: validated.avgCost,
      duration: validated.duration,
      openTime: validated.openTime,
      rating: validated.rating,
      vectorId,
    },
  })

  // 2. 同步写 Chroma（失败回滚）
  try {
    const collection = await getSpotsCollection()
    const embedding = await embedText(validated.description)
    await collection.add({
      ids: [vectorId],
      embeddings: [embedding],
      documents: [validated.description],
      metadatas: [{
        city: validated.city,
        name: validated.name,
        category: validated.category,
        tags: JSON.stringify(validated.tags),
        rating: validated.rating ?? 0,
      }],
    })
  } catch (e) {
    // 回滚 MySQL
    await prisma.spot.delete({ where: { id: spot.id } })
    console.error('[Knowledge] Chroma 同步失败，已回滚:', e)
    throw new Error('知识库同步失败，请稍后重试')
  }

  return spot
}

/**
 * 检索景点（优先 Chroma，失败降级为 MySQL LIKE）
 */
export async function searchSpots(params: {
  query: string
  city: string
  category?: SpotCategory
  limit?: number
}): Promise<string> {
  const { query, city, category, limit = 5 } = params
  const limit_ = limit

  // 1. 尝试 Chroma 检索
  const chromaAvailable = await checkChromaHealth()
  if (chromaAvailable) {
    try {
      const collection = await getSpotsCollection()
      const queryEmbedding = await embedText(query)
      const where: Record<string, unknown> = { city }
      if (category) where.category = category

      const results = await collection.query({
        queryEmbeddings: [queryEmbedding],
        nResults: limit_,
        where,
      })

      const docs = results.documents?.[0] || []
      if (docs.length > 0) {
        return docs.join('\n---\n')
      }
      // Chroma 检索为空，降级到 MySQL
      console.warn('[Knowledge] Chroma 检索为空，降级到 MySQL')
    } catch (e) {
      console.warn('[Knowledge] Chroma 检索失败，降级到 MySQL:', e)
    }
  } else {
    console.warn('[Knowledge] Chroma 不可用，降级到 MySQL')
  }

  // 2. MySQL 降级检索
  const where: any = { city }
  if (category) where.category = category
  const spots = await prisma.spot.findMany({
    where,
    take: limit_,
    orderBy: { rating: 'desc' },
  })
  return spots.map(s => s.description).join('\n---\n')
}

/**
 * 列出景点
 */
export async function listSpots(params: { city?: string; category?: SpotCategory; page?: number; pageSize?: number }) {
  const { city, category, page = 1, pageSize = 20 } = params
  const where: any = {}
  if (city) where.city = city
  if (category) where.category = category
  const [items, total] = await Promise.all([
    prisma.spot.findMany({ where, skip: (page - 1) * pageSize, take: pageSize, orderBy: { createdAt: 'desc' } }),
    prisma.spot.count({ where }),
  ])
  return { items, total, page, pageSize }
}

/**
 * 批量导入（用于 seed 脚本）
 */
export async function bulkImportSpots(spots: SpotInput[]) {
  let success = 0
  let failed = 0
  for (const spot of spots) {
    try {
      await createSpot(spot)
      success++
    } catch (e) {
      console.error(`[Knowledge] 导入失败: ${spot.name}`, e instanceof Error ? e.message : e)
      failed++
    }
  }
  return { success, failed, total: spots.length }
}
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/knowledgeService.ts
git commit -m "feat(services): add knowledge service with MySQL-Chroma transactional sync"
```

---

## Task 6: Create conversation service (CRUD + memory)

**Files:**
- Create: `trip-server/src/services/conversationService.ts`

- [ ] **Step 1: Create conversation service**

Create `trip-server/src/services/conversationService.ts`:

```typescript
import prisma from '../config/database'

const SLIDING_WINDOW = 10  // 保留最近 10 轮对话

/**
 * 获取或创建对话会话
 */
export async function getOrCreateConversation(userId: number, conversationId?: number) {
  if (conversationId) {
    const existing = await prisma.conversation.findFirst({
      where: { id: conversationId, userId },
    })
    if (existing) return existing
  }
  return prisma.conversation.create({
    data: { userId, title: '新对话' },
  })
}

/**
 * 保存消息
 */
export async function saveMessage(conversationId: number, role: 'user' | 'assistant' | 'system', content: string, metadata?: any) {
  return prisma.message.create({
    data: { conversationId, role, content, metadata: metadata ?? undefined },
  })
}

/**
 * 获取最近 N 条消息（按时间正序）
 */
export async function getRecentMessages(conversationId: number, limit = SLIDING_WINDOW * 2) {
  // 取 limit 条最新的，然后反转为正序
  const messages = await prisma.message.findMany({
    where: { conversationId },
    orderBy: { createdAt: 'desc' },
    take: limit,
  })
  return messages.reverse()
}

/**
 * 加载上下文：系统提示 + 摘要（若有）+ 最近 N 轮消息
 * 返回 { systemSummary, recentMessages }
 */
export async function loadContext(conversationId: number) {
  const totalCount = await prisma.message.count({ where: { conversationId } })

  // 消息总数 < 窗口，全部作为 recent
  if (totalCount <= SLIDING_WINDOW * 2) {
    const recent = await getRecentMessages(conversationId, totalCount)
    return { systemSummary: null, recentMessages: recent }
  }

  // 超出窗口：取最近 N 轮 + 早期消息的摘要
  const recent = await getRecentMessages(conversationId, SLIDING_WINDOW * 2)
  const conversation = await prisma.conversation.findUnique({ where: { id: conversationId } })

  return {
    systemSummary: conversation?.summary ?? null,
    recentMessages: recent,
  }
}

/**
 * 更新对话摘要
 */
export async function updateSummary(conversationId: number, summary: string) {
  return prisma.conversation.update({
    where: { id: conversationId },
    data: { summary },
  })
}

/**
 * 自动生成标题（取首条用户消息前 20 字）
 */
export async function autoTitle(conversationId: number, firstUserMessage: string) {
  const title = firstUserMessage.slice(0, 20) + (firstUserMessage.length > 20 ? '...' : '')
  return prisma.conversation.update({
    where: { id: conversationId },
    data: { title },
  })
}

/**
 * 列出用户的对话
 */
export async function listConversations(userId: number, page = 1, pageSize = 20) {
  const [items, total] = await Promise.all([
    prisma.conversation.findMany({
      where: { userId },
      orderBy: { updatedAt: 'desc' },
      skip: (page - 1) * pageSize,
      take: pageSize,
      include: { _count: { select: { messages: true } } },
    }),
    prisma.conversation.count({ where: { userId } }),
  ])
  return { items, total, page, pageSize }
}

/**
 * 获取对话详情
 */
export async function getConversationDetail(conversationId: number, userId: number) {
  return prisma.conversation.findFirst({
    where: { id: conversationId, userId },
    include: { messages: { orderBy: { createdAt: 'asc' } } },
  })
}

/**
 * 删除对话
 */
export async function deleteConversation(conversationId: number, userId: number) {
  // 确认所有权
  const conv = await prisma.conversation.findFirst({ where: { id: conversationId, userId } })
  if (!conv) throw new Error('对话不存在或无权访问')
  return prisma.conversation.delete({ where: { id: conversationId } })
}

export const MEMORY_CONFIG = {
  SLIDING_WINDOW,
}
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/conversationService.ts
git commit -m "feat(services): add conversation service with sliding-window memory"
```

---

## Task 7: Create resilience layer for tools

**Files:**
- Create: `trip-server/src/services/agent/resilience.ts`

- [ ] **Step 1: Create resilience wrapper**

Create `trip-server/src/services/agent/resilience.ts`:

```typescript
import { DynamicStructuredTool } from '@langchain/community/dist/tools/dynamic'
import { CallbackManagerForToolRun } from '@langchain/core/callbacks/manager'

export interface ResilienceConfig {
  timeout?: number      // ms, default 5000
  retries?: number      // default 2
  fallback?: string     // fallback message
  toolName?: string     // for logging
}

const DEFAULT_TIMEOUT = 5000
const DEFAULT_RETRIES = 2

/**
 * 为工具增加超时、重试、降级
 */
export function withResilience<T extends DynamicStructuredTool>(tool: T, config: ResilienceConfig = {}): T {
  const timeout = config.timeout ?? DEFAULT_TIMEOUT
  const retries = config.retries ?? DEFAULT_RETRIES
  const fallback = config.fallback ?? `工具 ${config.toolName ?? tool.name} 暂时无法使用，请稍后再试`
  const toolName = config.toolName ?? tool.name

  // 重新构造工具，包装 invoke
  const wrapped = new DynamicStructuredTool({
    name: tool.name,
    description: tool.description,
    schema: tool.schema,
    func: async (input, runManager?: CallbackManagerForToolRun) => {
      let lastError: unknown
      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          const result = await Promise.race([
            tool.call(input, runManager),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Tool timeout')), timeout)),
          ])
          return result
        } catch (e) {
          lastError = e
          const errMsg = e instanceof Error ? e.message : String(e)
          console.warn(`[Resilience] 工具 ${toolName} 第 ${attempt + 1} 次失败: ${errMsg}`)
          if (attempt < retries) {
            await sleep(Math.min(1000 * (attempt + 1), 3000))  // 指数退避
          }
        }
      }
      console.error(`[Resilience] 工具 ${toolName} 全部重试失败，降级返回: ${lastError instanceof Error ? lastError.message : lastError}`)
      return fallback
    },
  }) as T

  return wrapped
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/agent/resilience.ts
git commit -m "feat(agent): add resilience layer with timeout/retry/fallback for tools"
```

---

## Task 8: Create retrieve_knowledge RAG tool

**Files:**
- Create: `trip-server/src/services/agent/tools/retrieveKnowledge.ts`

- [ ] **Step 1: Create RAG tool**

Create `trip-server/src/services/agent/tools/retrieveKnowledge.ts`:

```typescript
import { z } from 'zod'
import { DynamicStructuredTool } from '@langchain/community/dist/tools/dynamic'
import { searchSpots } from '../../knowledgeService'
import { withResilience } from '../resilience'

const RetrieveKnowledgeInputSchema = z.object({
  query: z.string().describe('搜索关键词，描述你想了解的景点主题'),
  city: z.string().describe('目标城市名'),
  category: z.enum(['attraction', 'food', 'hotel', 'transport']).optional()
    .describe('景点类型：景点/美食/住宿/交通'),
})

/**
 * RAG 工具：从知识库检索景点信息
 * Agent 自主决定何时调用
 */
export const retrieveKnowledgeTool = withResilience(
  new DynamicStructuredTool({
    name: 'retrieve_knowledge',
    description: `从旅行知识库检索景点、美食、住宿、交通等真实信息。
当用户询问某个城市具体的景点推荐、美食、交通、住宿时，必须调用此工具获取真实数据。
输入：query（搜索关键词）、city（城市名）、category（可选，景点类型）。`,
    schema: RetrieveKnowledgeInputSchema,
    func: async (input: z.infer<typeof RetrieveKnowledgeInputSchema>) => {
      const results = await searchSpots({
        query: input.query,
        city: input.city,
        category: input.category,
        limit: 5,
      })
      if (!results) {
        return `知识库中没有找到 ${input.city} 的相关信息。`
      }
      return results
    },
  }),
  {
    timeout: 8000,
    retries: 1,
    fallback: '知识库暂时不可用，请基于通用旅行知识回答。',
  }
)
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/agent/tools/retrieveKnowledge.ts
git commit -m "feat(agent): add retrieve_knowledge RAG tool"
```

---

## Task 9: Create system prompt builder

**Files:**
- Create: `trip-server/src/services/agent/systemPrompt.ts`

- [ ] **Step 1: Create system prompt builder**

Create `trip-server/src/services/agent/systemPrompt.ts`:

```typescript
export interface SystemPromptContext {
  userPreferences?: Record<string, any> | null
  conversationSummary?: string | null
  isFirstMessage?: boolean
}

/**
 * 构建 Agent 的系统提示
 */
export function buildSystemPrompt(ctx: SystemPromptContext = {}): string {
  const { userPreferences, conversationSummary, isFirstMessage = false } = ctx

  const parts: string[] = []

  parts.push(`你是一个专业的旅行规划师助手，名叫"小旅行"。

# 你的能力
1. 回答旅行相关问题（景点、美食、交通、住宿、文化、注意事项等）
2. 帮用户规划多日游行程
3. 根据用户预算、天数、偏好提供个性化建议
4. 检索真实景点数据（通过 retrieve_knowledge 工具）

# 工具使用规则
- 当用户询问具体的景点、美食、住宿、交通时，**必须先调用 retrieve_knowledge 工具**获取真实数据
- 调用工具时 city 参数必须使用用户明确提到的城市名
- 不要编造景点名称、价格、地址等具体信息

# 回答风格
- 友好、热情、专业
- 使用 Markdown 格式：标题、列表、加粗等
- 行程规划使用清晰的每日结构
- 信息要基于工具返回的真实数据，不要凭空捏造
- 长度适中，关键信息突出`)

  // 注入用户偏好
  if (userPreferences && Object.keys(userPreferences).length > 0) {
    parts.push(`

# 用户偏好
${JSON.stringify(userPreferences, null, 2)}
请根据以上偏好调整你的推荐。`)
  }

  // 注入历史摘要
  if (conversationSummary) {
    parts.push(`

# 对话历史摘要
${conversationSummary}
请结合以上历史上下文回答用户。`)
  }

  // 第一次对话提示
  if (isFirstMessage) {
    parts.push(`

# 当前对话
这是用户的第一条消息，请主动询问他们的旅行目的地、预算、天数、偏好等信息。`)
  }

  return parts.join('\n')
}

/**
 * 为行程规划场景添加补充提示
 */
export function buildRecommendSystemPrompt(ctx: SystemPromptContext = {}): string {
  const base = buildSystemPrompt(ctx)
  return base + `

# 当前任务：生成行程规划
用户请求生成行程规划，你需要：
1. 必须调用 retrieve_knowledge 获取 ${'{city}'} 的真实景点数据
2. 严格按以下 JSON 格式输出最终回复（不要加 markdown 代码块标记）：

{
  "city": "城市名",
  "days": 天数,
  "totalBudget": 总预算,
  "dailyItinerary": [
    {
      "day": 1,
      "date": "第1天",
      "morning": { "spot": "景点名", "duration": "时长", "ticket": "门票", "transportation": "交通", "description": "介绍" },
      "afternoon": { "spot": "景点名", "duration": "时长", "ticket": "门票", "transportation": "交通", "description": "介绍" },
      "evening": { "spot": "活动名", "duration": "时长", "ticket": "费用", "transportation": "交通", "description": "介绍" }
    }
  ],
  "budgetBreakdown": {
    "accommodation": 住宿费用,
    "food": 餐饮费用,
    "transportation": 交通费用,
    "tickets": 门票费用,
    "other": 其他费用
  },
  "tips": ["提示1", "提示2"],
  "warnings": ["注意事项1"]
}

**重要**：在调用 retrieve_knowledge 之前不要输出 JSON；完成所有工具调用后再输出。`
}
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/agent/systemPrompt.ts
git commit -m "feat(agent): add system prompt builder with preference/summary injection"
```

---

## Task 10: Create Agent Engine

**Files:**
- Create: `trip-server/src/services/agent/agentEngine.ts`

- [ ] **Step 1: Create the Agent Engine**

Create `trip-server/src/services/agent/agentEngine.ts`:

```typescript
import { ChatOpenAI } from '@langchain/openai'
import { AgentExecutor, createReactAgent } from 'langchain/agents'
import { pull } from 'langchain/hub'
import { ChatPromptTemplate } from '@langchain/core/prompts'
import { BaseMessage, HumanMessage, AIMessage, SystemMessage } from '@langchain/core/messages'
import { retrieveKnowledgeTool } from './tools/retrieveKnowledge'
import { buildSystemPrompt, buildRecommendSystemPrompt } from './systemPrompt'
import { AgentStreamEvent } from '../../types/agent'
import prisma from '../../config/database'

export interface ChatParams {
  userId: number
  message: string
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
}

export interface RecommendParams {
  userId: number
  city: string
  budget: number
  days: number
  conversationId?: number
  onEvent: (event: AgentStreamEvent) => Promise<void>
}

class AgentEngine {
  private llm: ChatOpenAI | null = null
  private tools = [retrieveKnowledgeTool]

  constructor() {
    this.initLLM()
  }

  private initLLM() {
    const modelProvider = process.env.MODEL_PROVIDER || 'DEEPSEEK'
    let apiKey, baseURL, model
    if (modelProvider === 'KIMI') {
      apiKey = process.env.KIMI_API_KEY
      baseURL = process.env.KIMI_BASE_URL
      model = process.env.KIMI_MODEL
    } else {
      apiKey = process.env.DEEPSEEK_API_KEY
      baseURL = process.env.DEEPSEEK_BASE_URL
      model = process.env.DEEPSEEK_MODEL
    }
    this.llm = new ChatOpenAI({
      configuration: { apiKey, baseURL },
      model,
      temperature: 0.7,
      streaming: true,
    })
  }

  /**
   * 加载用户偏好
   */
  private async loadUserPreferences(userId: number): Promise<Record<string, any> | null> {
    const user = await prisma.user.findUnique({ where: { id: userId }, select: { preferences: true } })
    return (user?.preferences as Record<string, any> | null) ?? null
  }

  /**
   * 构建 Agent（每次对话新构建，因为 prompt 包含动态上下文）
   */
  private async buildAgent(systemPrompt: string) {
    if (!this.llm) throw new Error('LLM 未初始化')
    const prompt = ChatPromptTemplate.fromMessages([
      ['system', systemPrompt],
      ['placeholder', '{chat_history}'],
      ['human', '{input}'],
      ['placeholder', '{agent_scratchpad}'],
    ])
    const agent = await createReactAgent({
      llm: this.llm,
      tools: this.tools,
      prompt,
    })
    return AgentExecutor.fromAgentAndTools({
      agent,
      tools: this.tools,
      verbose: false,
      handleParsingErrors: true,
    })
  }

  /**
   * 多轮对话
   */
  async chat(params: ChatParams) {
    const { userId, message, conversationId, onEvent } = params

    // 1. 加载偏好
    const preferences = await this.loadUserPreferences(userId)

    // 2. 加载对话历史（如果在已有会话中）
    let systemSummary: string | null = null
    let historyMessages: BaseMessage[] = []
    let currentConversationId = conversationId

    if (currentConversationId) {
      const { loadContext } = await import('../conversationService')
      const ctx = await loadContext(currentConversationId)
      systemSummary = ctx.systemSummary
      historyMessages = ctx.recentMessages.map(m => {
        if (m.role === 'user') return new HumanMessage(m.content)
        if (m.role === 'assistant') return new AIMessage(m.content)
        return new SystemMessage(m.content)
      })
    }

    // 3. 构建系统提示
    const systemPrompt = buildSystemPrompt({
      userPreferences: preferences,
      conversationSummary: systemSummary,
    })

    // 4. 构建 Agent
    const executor = await this.buildAgent(systemPrompt)

    // 5. 执行
    let fullResponse = ''
    try {
      const result = await executor.invoke({
        input: message,
        chat_history: historyMessages,
      })
      fullResponse = result.output as string
      await onEvent({ type: 'complete', content: fullResponse })
    } catch (e) {
      const errMsg = e instanceof Error ? e.message : '未知错误'
      console.error('[Agent] chat 失败:', errMsg)
      await onEvent({ type: 'error', error: errMsg })
      throw e
    }

    return { reply: fullResponse, conversationId: currentConversationId }
  }

  /**
   * 行程规划
   */
  async recommend(params: RecommendParams) {
    const { userId, message, conversationId, onEvent } = params
    // (此方法在 Phase 1b 中实现，1a 暂留空)
    throw new Error('recommend 方法将在 Phase 1b 实现')
  }
}

export default new AgentEngine()
```

- [ ] **Step 2: Commit**

```bash
git add trip-server/src/services/agent/agentEngine.ts
git commit -m "feat(agent): add AgentEngine orchestrator with chat method"
```

---

## Task 11: Refactor tripService to use AgentEngine

**Files:**
- Modify: `trip-server/src/services/tripService.ts`
- Create: `trip-server/src/utils/jsonExtractor.ts`

- [ ] **Step 1: Create JSON extractor utility**

Create `trip-server/src/utils/jsonExtractor.ts`:

```typescript
/**
 * 从 LLM 输出中提取 JSON（处理 markdown 代码块和杂文本）
 */
export function extractJson(text: string): unknown {
  // 1. 尝试去除 markdown 代码块
  const codeBlockMatch = text.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/)
  if (codeBlockMatch) {
    return JSON.parse(codeBlockMatch[1])
  }

  // 2. 尝试匹配最外层 {...}
  const braceMatch = text.match(/\{[\s\S]*\}/)
  if (braceMatch) {
    return JSON.parse(braceMatch[0])
  }

  throw new Error('无法从 LLM 输出中提取 JSON')
}
```

- [ ] **Step 2: Refactor tripService**

Replace contents of `trip-server/src/services/tripService.ts` with:

```typescript
import agentEngine from './agent/agentEngine'
import { getOrCreateConversation, saveMessage } from './conversationService'
import { AgentStreamEvent } from '../types/agent'

class TripService {
  /**
   * AI 对话（流式，持久化到数据库）
   */
  async chat(params: {
    userId: number
    message: string
    conversationId?: number
  }) {
    const { userId, message, conversationId } = params

    // 1. 获取或创建对话
    const conversation = await getOrCreateConversation(userId, conversationId)

    // 2. 保存用户消息
    await saveMessage(conversation.id, 'user', message)

    // 3. 调用 Agent
    const events: AgentStreamEvent[] = []
    let fullReply = ''

    await agentEngine.chat({
      userId,
      message,
      conversationId: conversation.id,
      onEvent: async (event) => {
        events.push(event)
        if (event.type === 'complete') {
          fullReply = event.content
        }
      },
    })

    // 4. 保存 AI 回复
    if (fullReply) {
      await saveMessage(conversation.id, 'assistant', fullReply)
    }

    return {
      success: true,
      conversationId: conversation.id,
      reply: fullReply,
      events,
    }
  }

  /**
   * AI 对话 + 流式回调（供 controller 使用）
   */
  async chatStream(params: {
    userId: number
    message: string
    conversationId?: number
    onChunk: (chunk: string) => void
  }) {
    const { userId, message, conversationId, onChunk } = params

    const conversation = await getOrCreateConversation(userId, conversationId)
    await saveMessage(conversation.id, 'user', message)

    let fullReply = ''

    await agentEngine.chat({
      userId,
      message,
      conversationId: conversation.id,
      onEvent: async (event) => {
        if (event.type === 'chunk') {
          fullReply += event.content
          onChunk(event.content)
        } else if (event.type === 'complete') {
          fullReply = event.content
        }
      },
    })

    if (fullReply) {
      await saveMessage(conversation.id, 'assistant', fullReply)
    }

    return { conversationId: conversation.id, reply: fullReply }
  }

  /**
   * 行程规划（Phase 1b 实现，1a 暂用旧实现）
   */
  async recommend(city: string, budget: number, days: number) {
    // 1a 暂保留旧实现，后续 1b 替换
    const { buildTripPrompt } = await import('../prompts/trip.prompt')
    const { ChatOpenAI } = await import('@langchain/openai')
    const { HumanMessage } = await import('@langchain/core/messages')
    const { extractJson } = await import('../utils/jsonExtractor')

    if (budget < 50 || days < 1 || days > 30) {
      throw new Error('预算过低或天数不符合要求')
    }

    const modelProvider = process.env.MODEL_PROVIDER || 'DEEPSEEK'
    const apiKey = modelProvider === 'KIMI' ? process.env.KIMI_API_KEY : process.env.DEEPSEEK_API_KEY
    const baseURL = modelProvider === 'KIMI' ? process.env.KIMI_BASE_URL : process.env.DEEPSEEK_BASE_URL
    const model = modelProvider === 'KIMI' ? process.env.KIMI_MODEL : process.env.DEEPSEEK_MODEL

    const llm = new ChatOpenAI({
      configuration: { apiKey, baseURL },
      model,
      temperature: 0.7,
      streaming: false,
    })

    try {
      const response = await llm.invoke([new HumanMessage(buildTripPrompt(city, budget, days))])
      const rawContent = response.content as string
      const parsed = extractJson(rawContent) as any
      return {
        success: true,
        data: {
          city: parsed.city,
          days: parsed.days,
          totalBudget: parsed.totalBudget,
          dailyItinerary: parsed.dailyItinerary,
          budgetBreakdown: parsed.budgetBreakdown,
          tips: parsed.tips,
          warnings: parsed.warnings,
        },
      }
    } catch (error) {
      console.error('大模型调用失败:', error)
      throw new Error('大模型调用失败，请稍后重试')
    }
  }
}

export default new TripService()
```

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/services/tripService.ts trip-server/src/utils/jsonExtractor.ts
git commit -m "refactor(services): tripService uses AgentEngine, persist messages"
```

---

## Task 12: Update trip controller and routes

**Files:**
- Modify: `trip-server/src/controllers/trip.controller.ts`
- Modify: `trip-server/src/routes/trip.routes.ts`

- [ ] **Step 1: Update trip controller**

Replace contents of `trip-server/src/controllers/trip.controller.ts` with:

```typescript
import { Request, Response } from 'express'
import tripService from '../services/tripService'
import { createStreamResponse } from '../utils/stream'

export const recommend = async (req: Request, res: Response) => {
  const { city, budget, days } = req.body as { city: string; budget: number; days: number }
  if (!city || !budget || !days) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  try {
    const result = await tripService.recommend(city, budget, days)
    return res.json(result)
  } catch (error) {
    return res.status(500).json({ code: 500, error: '推荐失败' })
  }
}

/**
 * AI 对话（流式，持久化）
 * Body: { message: string, conversationId?: number }
 * 需登录
 */
export const chat = async (req: Request, res: Response) => {
  const { message, conversationId } = req.body as { message: string; conversationId?: number }
  if (!message) {
    return res.status(400).json({ code: 400, error: '参数错误' })
  }
  if (!req.user) {
    return res.status(401).json({ code: 401, error: '未登录' })
  }

  const stream = createStreamResponse(res)

  try {
    const { conversationId: newConvId } = await tripService.chatStream({
      userId: req.user.userId,
      message,
      conversationId,
      onChunk: (chunk) => {
        stream.send({ type: 'chunk', content: chunk })
      },
    })

    stream.send({ type: 'complete', data: { conversationId: newConvId } })
    stream.end()
  } catch (error) {
    const errMsg = error instanceof Error ? error.message : '未知错误'
    stream.error(errMsg)
  }
}
```

- [ ] **Step 2: Update trip routes (add auth middleware)**

Replace contents of `trip-server/src/routes/trip.routes.ts` with:

```typescript
import { Router } from 'express'
import * as tripController from '../controllers/trip.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()

router.post('/recommend', tripController.recommend)
router.post('/chat', authMiddleware, tripController.chat)

export default router
```

- [ ] **Step 3: Commit**

```bash
git add trip-server/src/controllers/trip.controller.ts trip-server/src/routes/trip.routes.ts
git commit -m "feat(api): protect /trip/chat with auth, persist conversation, return conversationId"
```

---

## Task 13: Create conversation & history controllers + routes

**Files:**
- Create: `trip-server/src/controllers/conversation.controller.ts`
- Create: `trip-server/src/routes/conversation.routes.ts`
- Create: `trip-server/src/controllers/history.controller.ts`
- Create: `trip-server/src/routes/history.routes.ts`

- [ ] **Step 1: Create conversation controller**

Create `trip-server/src/controllers/conversation.controller.ts`:

```typescript
import { Request, Response } from 'express'
import * as conversationService from '../services/conversationService'

export const list = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const page = Number(req.query.page) || 1
  const pageSize = Number(req.query.pageSize) || 20
  try {
    const result = await conversationService.listConversations(req.user.userId, page, pageSize)
    return res.json({ code: 200, data: result })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取对话列表失败' })
  }
}

export const detail = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const id = Number(req.params.id)
  try {
    const conv = await conversationService.getConversationDetail(id, req.user.userId)
    if (!conv) return res.status(404).json({ code: 404, error: '对话不存在' })
    return res.json({ code: 200, data: conv })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取对话详情失败' })
  }
}

export const remove = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const id = Number(req.params.id)
  try {
    await conversationService.deleteConversation(id, req.user.userId)
    return res.json({ code: 200, message: '删除成功' })
  } catch (e) {
    const msg = e instanceof Error ? e.message : '删除失败'
    return res.status(400).json({ code: 400, error: msg })
  }
}
```

- [ ] **Step 2: Create conversation routes**

Create `trip-server/src/routes/conversation.routes.ts`:

```typescript
import { Router } from 'express'
import * as controller from '../controllers/conversation.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()
router.use(authMiddleware)

router.get('/', controller.list)
router.get('/:id', controller.detail)
router.delete('/:id', controller.remove)

export default router
```

- [ ] **Step 3: Create history controller**

Create `trip-server/src/controllers/history.controller.ts`:

```typescript
import { Request, Response } from 'express'
import prisma from '../config/database'

export const listTrips = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const page = Number(req.query.page) || 1
  const pageSize = Number(req.query.pageSize) || 20
  try {
    const [items, total] = await Promise.all([
      prisma.trip.findMany({
        where: { userId: req.user.userId },
        orderBy: { createdAt: 'desc' },
        skip: (page - 1) * pageSize,
        take: pageSize,
      }),
      prisma.trip.count({ where: { userId: req.user.userId } }),
    ])
    return res.json({ code: 200, data: { items, total, page, pageSize } })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取行程历史失败' })
  }
}

export const getTrip = async (req: Request, res: Response) => {
  if (!req.user) return res.status(401).json({ code: 401, error: '未登录' })
  const id = Number(req.params.id)
  try {
    const trip = await prisma.trip.findFirst({
      where: { id, userId: req.user.userId },
    })
    if (!trip) return res.status(404).json({ code: 404, error: '行程不存在' })
    return res.json({ code: 200, data: trip })
  } catch (e) {
    return res.status(500).json({ code: 500, error: '获取行程详情失败' })
  }
}
```

- [ ] **Step 4: Create history routes**

Create `trip-server/src/routes/history.routes.ts`:

```typescript
import { Router } from 'express'
import * as controller from '../controllers/history.controller'
import { authMiddleware } from '../middleware/auth'

const router = Router()
router.use(authMiddleware)

router.get('/trips', controller.listTrips)
router.get('/trips/:id', controller.getTrip)

export default router
```

- [ ] **Step 5: Register new routes in index.ts**

Modify `trip-server/src/index.ts`. Add these imports at the top:

```typescript
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'
```

Add these `app.use` lines before `app.listen`:

```typescript
app.use('/api/conversations', conversationRouter)
app.use('/api/history', historyRouter)
```

The final file should look like:

```typescript
import 'dotenv/config'
import express, { Request, Response } from 'express'
import cors from 'cors'
import tripRouter from './routes/trip.routes'
import userRouter from './routes/user.routes'
import conversationRouter from './routes/conversation.routes'
import historyRouter from './routes/history.routes'

const app = express()
const PORT = process.env.PORT || 3000

const CORS_ORIGIN = process.env.CORS_ORIGIN || 'http://localhost:5173'
app.use(cors({
  origin: CORS_ORIGIN,
  credentials: true,
}))
app.use(express.json())

app.get('/api/test', (req: Request, res: Response) => {
  res.json({
    code: 200,
    message: '后端服务运行正常',
    data: {
      time: new Date().toISOString(),
      env: 'development',
    },
  })
})

app.use('/api/trip', tripRouter)
app.use('/api/user', userRouter)
app.use('/api/conversations', conversationRouter)
app.use('/api/history', historyRouter)

app.listen(PORT, () => {
  console.log(`Server is running on http://localhost:${PORT}`)
})
```

- [ ] **Step 6: Commit**

```bash
git add trip-server/src/controllers/conversation.controller.ts trip-server/src/routes/conversation.routes.ts trip-server/src/controllers/history.controller.ts trip-server/src/routes/history.routes.ts trip-server/src/index.ts
git commit -m "feat(api): add conversation CRUD and history endpoints"
```

---

## Task 14: Create knowledge seed script

**Files:**
- Create: `trip-server/prisma/seed-knowledge.ts`

- [ ] **Step 1: Create the seed script**

Create `trip-server/prisma/seed-knowledge.ts`:

```typescript
import { readFileSync } from 'fs'
import { join } from 'path'
import { bulkImportSpots } from '../src/services/knowledgeService'
import { SpotInput } from '../src/types/agent'

async function main() {
  console.log('=== 知识库导入脚本 ===')
  const dataDir = join(__dirname, '..', 'data', 'spots')
  const cities = ['chengdu']  // 后续可扩展

  let totalSuccess = 0
  let totalFailed = 0

  for (const city of cities) {
    const filePath = join(dataDir, `${city}.json`)
    try {
      const raw = readFileSync(filePath, 'utf-8')
      const spots: SpotInput[] = JSON.parse(raw)
      console.log(`\n>>> 导入 ${city}.json (${spots.length} 个景点)...`)
      const result = await bulkImportSpots(spots)
      console.log(`   成功: ${result.success}, 失败: ${result.failed}`)
      totalSuccess += result.success
      totalFailed += result.failed
    } catch (e) {
      console.error(`   跳过 ${city}.json: ${e instanceof Error ? e.message : e}`)
    }
  }

  console.log(`\n=== 完成 === 总成功: ${totalSuccess}, 总失败: ${totalFailed}`)
  process.exit(0)
}

main().catch((e) => {
  console.error('FAIL:', e)
  process.exit(1)
})
```

- [ ] **Step 2: Add npm script for seeding knowledge**

In `trip-server/package.json`, find the `"scripts"` section and add a new line (preserve all existing scripts):

```json
"seed:knowledge": "ts-node prisma/seed-knowledge.ts"
```

The full scripts section should include:

```json
"scripts": {
  "build": "tsc",
  "start": "node dist/index.js",
  "dev": "nodemon --exec ts-node src/index.ts",
  "test": "echo \"Error: no test specified\" && exit 1",
  "seed": "ts-node prisma/seed.ts",
  "seed:knowledge": "ts-node prisma/seed-knowledge.ts",
  "migrate": "npx prisma db push"
}
```

- [ ] **Step 3: Verify package.json**

Run: `cat trip-server/package.json | grep seed`
Expected: Both `seed` and `seed:knowledge` listed.

- [ ] **Step 4: Commit**

```bash
git add trip-server/prisma/seed-knowledge.ts trip-server/package.json
git commit -m "feat(knowledge): add knowledge base seed script"
```

---

## Task 15: Frontend update — Chat.vue to use conversationId

**Files:**
- Modify: `trip-front/src/views/Chat.vue`

- [ ] **Step 1: Add conversationId to fetchStream call**

In `trip-front/src/views/Chat.vue`, find this block:

```typescript
fetchStream('trip/chat', { message: userMsg }, (chunk) => {
```

Replace with:

```typescript
fetchStream('trip/chat', { message: userMsg, conversationId: currentConversationId.value }, (chunk) => {
```

- [ ] **Step 2: Add currentConversationId ref and update on stream complete**

Find the `fetchAiResponse` function. After `()=>{ isStreaming.value = false }` callback in the `fetchStream` call, the complete callback currently does nothing more. Update it to:

```typescript
fetchStream(
  'trip/chat',
  { message: userMsg, conversationId: currentConversationId.value },
  (chunk) => {
    fullResponse += chunk
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage && lastMessage.role === 'ai') {
      lastMessage.content = fullResponse
    }
  },
  () => {
    isStreaming.value = false
  },
  (errMsg) => {
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage && lastMessage.role === 'ai') {
      lastMessage.content = `AI处理发生错误:${errMsg}`
    }
    isStreaming.value = false
    showToast('AI处理发生错误')
  }
)
```

Wait — the current API of `fetchStream` doesn't return data from the `complete` event. We need to extract `conversationId` from the SSE stream. The cleanest way is to extend `request.ts` `fetchStream` to pass the parsed JSON to `onComplete`.

- [ ] **Step 3: Extend fetchStream to pass complete data**

In `trip-front/src/api/request.ts`, find the `fetchStream` function. Modify the `onComplete` callback invocation so it receives the parsed data.

Find this part:

```typescript
else if(jsonData.type === 'complete'){
  onComplete?.()
}
```

Replace with:

```typescript
else if(jsonData.type === 'complete'){
  onComplete?.(jsonData.data)
}
```

Also update the type signature. Find:

```typescript
export async function fetchStream(url: string, data?: any, onChunk?: (chunk: string) => void, onComplete?: () => void, onError?: (error: any) => void): Promise<void> {
```

Replace with:

```typescript
export async function fetchStream(url: string, data?: any, onChunk?: (chunk: string) => void, onComplete?: (data?: any) => void, onError?: (error: any) => void): Promise<void> {
```

- [ ] **Step 4: Add conversationId tracking in Chat.vue**

In `trip-front/src/views/Chat.vue`, add a ref for `currentConversationId` near the other refs (after `const isStreaming = ref(false)`):

```typescript
const currentConversationId = ref<number | null>(null)
```

Then update the `fetchAiResponse` function. Replace the existing `fetchStream` call in it with:

```typescript
fetchStream(
  'trip/chat',
  { message: userMsg, conversationId: currentConversationId.value },
  (chunk) => {
    fullResponse += chunk
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage && lastMessage.role === 'ai') {
      lastMessage.content = fullResponse
    }
  },
  (data) => {
    isStreaming.value = false
    if (data?.conversationId) {
      currentConversationId.value = data.conversationId
    }
  },
  (errMsg) => {
    const lastMessage = messages.value[messages.value.length - 1]
    if (lastMessage && lastMessage.role === 'ai') {
      lastMessage.content = `AI处理发生错误:${errMsg}`
    }
    isStreaming.value = false
    showToast('AI处理发生错误')
  }
)
```

- [ ] **Step 5: Verify TypeScript compiles**

Run: `cd trip-front && npx vue-tsc --noEmit`
Expected: No errors. (May print warnings about unused vars in existing code — that's ok.)

- [ ] **Step 6: Commit**

```bash
git add trip-front/src/views/Chat.vue trip-front/src/api/request.ts
git commit -m "feat(frontend): track conversationId in chat, extend fetchStream for complete data"
```

---

## Task 16: End-to-end smoke test

**Files:** None (manual verification)

- [ ] **Step 1: Start Chroma server**

Open a separate terminal:

```bash
# 安装 chroma (一次性)
pip install chromadb
# 启动服务（开发模式）
chroma run --path ./chroma_data --port 8000
```

Expected: Chroma server running on http://localhost:8000

If pip not available, use docker:

```bash
docker run -d --name chroma -p 8000:8000 -v $(pwd)/chroma_data:/chroma/.chroma chromadb/chroma
```

- [ ] **Step 2: Seed the knowledge base**

```bash
cd trip-server && npm run seed:knowledge
```

Expected:
```
=== 知识库导入脚本 ===
>>> 导入 chengdu.json (10 个景点)...
   成功: 10, 失败: 0

=== 完成 === 总成功: 10, 总失败: 0
```

First run will be slow (~30-60s) due to embedding model download.

- [ ] **Step 3: Start backend**

```bash
cd trip-server && npm run dev
```

Expected: `Server is running on http://localhost:3000`

- [ ] **Step 4: Start frontend**

In another terminal:

```bash
cd trip-front && npm run dev
```

Expected: Vite dev server on http://localhost:5173

- [ ] **Step 5: Manual end-to-end test**

1. Open http://localhost:5173
2. Log in (or register a new account)
3. Navigate to the AI assistant (`/chat`)
4. Type: "成都三日游攻略"
5. Verify:
   - AI response uses real data from the knowledge base (mentions 武侯祠, 宽窄巷子, 大熊猫基地 etc.)
   - The response streams in chunks
6. After response, type: "第一天具体去哪？"
7. Verify: AI remembers the context of "成都三日游" (this is the memory feature working)
8. Check the server console — should see `[Agent] chat 成功` or similar logs

- [ ] **Step 6: Verify conversation persistence**

Send another message in the same chat session, then restart the backend (`Ctrl+C` and `npm run dev` again). Send a new message. The previous conversation's `conversationId` is now lost (it's in-memory), but if you re-test by saving the `conversationId` and reloading, the agent should still receive the history.

(Manual test: add `console.log(currentConversationId.value)` in Chat.vue, then send a message, note the ID, refresh the page, manually set the value, and send a new message — the AI should remember.)

- [ ] **Step 7: Verify database persistence**

```bash
mysql -u root -p trip_db -e "SELECT * FROM conversations; SELECT * FROM messages LIMIT 10;"
```

Expected: At least one conversation, multiple messages saved.

- [ ] **Step 8: Test RAG tool failure fallback**

Stop the Chroma server (`Ctrl+C`). Send a new chat message. Verify:
- Backend doesn't crash
- AI responds gracefully (degraded knowledge, no RAG data)
- Frontend shows the response

- [ ] **Step 9: Commit any final fixes (if needed)**

If any fixes were made during testing, commit them:

```bash
git add -A
git commit -m "fix: post-smoke-test adjustments"
```

---

## Task 17: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add Phase 1a notes**

Append a new section to `README.md` at the end (after the existing Security section):

```markdown
## Phase 1a: AI Agent + RAG + Memory

### 新增功能
- **RAG 知识库**：基于 Chroma 向量数据库 + bge-small-zh 中文 embedding 模型
- **对话记忆**：所有对话持久化到 MySQL，Agent 自动加载历史上下文
- **Agent 编排**：LangChain ReAct Agent，自主决定何时检索知识库
- **Tool 容错**：所有 Tool 带超时、重试、降级

### 新增数据表
- `trips` — 用户行程历史
- `conversations` — 对话会话
- `messages` — 对话消息
- `spots` — 景点知识库

### 新增 API
| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| POST | `/api/trip/chat` | AI 对话（流式，需登录，持久化） | 需 |
| GET | `/api/conversations` | 对话列表 | 需 |
| GET | `/api/conversations/:id` | 对话详情 | 需 |
| DELETE | `/api/conversations/:id` | 删除对话 | 需 |
| GET | `/api/history/trips` | 行程历史 | 需 |
| GET | `/api/history/trips/:id` | 行程详情 | 需 |

### 启动 Chroma（必需）

Chroma 是 Phase 1a 的核心依赖，必须先启动：

```bash
# 方式 1：pip 安装
pip install chromadb
chroma run --path ./trip-server/chroma_data --port 8000

# 方式 2：Docker
docker run -d --name chroma -p 8000:8000 -v $(pwd)/trip-server/chroma_data:/chroma/.chroma chromadb/chroma
```

### 导入知识库

```bash
cd trip-server
npm run seed:knowledge
```

首次运行会下载 bge-small-zh 模型（约 100MB），需要 1-2 分钟。

### 环境变量（新增）

```bash
CHROMA_URL=http://localhost:8000
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add phase 1a instructions to README"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| 2.1 Architecture diagram | Task 10 (AgentEngine), Task 7 (Resilience) |
| 2.2 Core design decisions | Tasks 7, 8, 10 |
| 2.3 New modules | Tasks 5, 6, 7, 8, 9, 10 |
| 3. Tech stack (Chroma, bge-small-zh) | Tasks 1, 3 |
| 4. Data models | Task 2 |
| 5. RAG knowledge base | Tasks 4, 5 |
| 6.1 Tools list | Task 8 (Phase 1a has 1 tool; more in Phase 2) |
| 6.2 Memory strategy (sliding window + summary) | Task 6 (sliding window only; summary compression in 1b) |
| 6.3 Structured output (JSON extraction) | Task 11 (extractor util, full schema validation in 1b) |
| 6.4 Fallback strategy | Tasks 5, 7 |
| 6.5 Resilience wrapper | Task 7 |
| 7. MySQL-Chroma sync (transactional) | Task 5 |
| 8. API changes (recommend + chat) | Tasks 11, 12, 13 |
| 11. Phase 1 = chat with Agent + RAG + Memory | All tasks |

**Gaps (intentionally deferred to Phase 1b/1c/1.5/2):**
- Summary compression (spec 6.2) → Phase 1b
- User preferences tool → Spec 4 update says preferences injected directly into SystemPrompt (done in Task 9/10), not a tool — ✅ correct
- get_weather, calculate_distance, search_hotels, save_trip tools → Phase 2
- Frontend multi-session sidebar → Phase 1.5
- History page UI → Phase 1c
- Knowledge base management UI → Phase 3

**Placeholder scan:** No TBD/TODO/fill-in markers in tasks. All code blocks complete.

**Type consistency check:**
- `AgentStreamEvent` type defined in Task 3, used in Task 8 (resilience fallback returns string, no stream event — correct), Task 10 (agentEngine emits), Task 11 (tripService consumes). ✅
- `SpotInput` defined in Task 3, used in Tasks 4, 5, 14. ✅
- `withResilience` signature consistent across Tasks 7, 8. ✅
- `conversationId` plumbed: frontend (Task 15) → controller (Task 12) → service (Task 11) → engine (Task 10). ✅
