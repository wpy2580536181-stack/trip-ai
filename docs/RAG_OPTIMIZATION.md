# RAG 知识库四层优化 — 完整文档

## 目录

1. [背景与目标](#1-背景与目标)
2. [Phase 1: 索引层优化](#phase-1-索引层优化)
3. [Phase 2: 查询改写](#phase-2-查询改写query-rewriting)
4. [Phase 3: 多路召回 + RRF 融合](#phase-3-多路召回--rrf-融合)
5. [Phase 4: Cross-Encoder 重排序](#phase-4-cross-encoder-重排序)
6. [完整检索链路](#完整检索链路)
7. [文件清单](#文件清单)

---

## 1. 背景与目标

### 优化前状态

| 维度 | 状态 |
|------|------|
| 数据规模 | 754 条 Spot，30 个城市 |
| Embedding | 仅 `description` 字段，`bge-small-zh-v1.5`，512 维 |
| 向量存储 | ChromaDB v1.4.4，cosine similarity |
| 检索 | 单路：Chroma 向量检索 → MySQL LIKE 降级 |
| 召回数量 | `limit=5` 硬编码，无重排序 |
| 查询处理 | 直接使用用户原始 query |

### 优化目标

1. **索引层**：让 embedding 包含更多语义信号（名称、城市、标签、分类）
2. **查询层**：将自然语言 query 改写为检索友好的关键词
3. **召回层**：多路并行召回，用 RRF 融合去重，最大化召回率
4. **排序层**：用 Cross-Encoder 对候选做精排，提升精确率

---

## Phase 1: 索引层优化

### 1.1 问题分析

**原有做法**：`createSpot` 中仅对 `description` 字段做 embedding，存入 Chroma。

```typescript
// 优化前（仅 description）
const embedding = await embedText(validated.description)
await collection.add({ documents: [validated.description], ... })
```

**问题**：
- `description` 字段信息密度低，缺少 `name`（强信号词）、`tags`（分类标签）、`city`（地理约束）等高权重字段
- 查询"火锅"时，embedding 无法命中那些 description 中未显式出现"火锅"二字的正确结果

### 1.2 解决方案：多字段拼接

**思路**：将 `city`、`name`、`description`、`tags`、`category` 拼接为单一文档再 embedding。

**拼接顺序**：`city + name + description + tags + category`

> **为什么 city 在最前**：embedding 模型对序列开头的位置最敏感（position bias），城市名作为强地理约束应放在最前。

```typescript
// 优化后
function buildEmbeddingDocument(spot: SpotInput): string {
  const tags = Array.isArray(spot.tags) ? spot.tags.join(' ') : ''
  return `${spot.city} ${spot.name} ${spot.description} ${tags} ${spot.category}`
}
```

**metadata 不变**：仅改 `documents` 和 `embedding` 输入，`metadatas` 字段保持不变用于 Chroma 的 `where` 过滤。

### 1.3 迁移方案

已有 754 条数据仍是旧格式 embedding，需要一次性重 embedding。

**迁移脚本**：`scripts/re-embed-spreads.ts`

```
流程:
1. 从 MySQL 读取全部 Spot（含 vectorId, name, city, description, tags, category）
2. 对每条生成拼接后的 docText
3. 调用 embedText() 生成新 embedding
4. 用 Chroma update() 原子更新（不中断服务）
5. 报告：成功/失败数量
```

**执行结果**：

```
========== 迁移报告 ==========
成功: 754
跳过 (无 vectorId): 0
失败: 0
```

### 1.4 效果验证

| Query | 优化前 | 优化后 |
|---|---|---|
| "火锅" | 可能命中不到 | 名称含"火锅"的店排在前列 |
| "好吃的" | 依赖 description 中的美食描述 | 名称 + tags 中的"小吃""川菜"直接命中 |

---

## Phase 2: 查询改写（Query Rewriting）

### 2.1 问题分析

用户输入的是自然语言，但向量检索对关键词的匹配更敏感：

| 用户输入 | 问题 |
|---|---|
| "我想吃点辣的" | embedding 包含"我""想""点"等停用词，信号被稀释 |
| "带小孩去玩的" | 向量检索不知道"小孩"对应"亲子""儿童""乐园" |
| "成都有什么好玩的" | "有什么"是无效查询词 |

### 2.2 解决方案：LLM 查询改写

**核心思路**：在 `searchSpots` 入口处调用 LLM（DeepSeek/Kimi），将自然语言 query 改写为关键词组合。

**实现文件**：`src/services/queryRewriter.ts`

**Prompt 设计**：

```
system: 你是一个旅行查询改写专家...
规则:
1. 保留核心实体（城市名、景点类型如"火锅""博物馆""公园"）
2. 提取隐含意图（"想吃的"→"美食 餐厅"）
3. 用空格分隔最多 8 个词
4. 不要加解释，只输出关键词

示例:
"我想吃点辣的" → "川菜 湘味 辣味 火锅 餐厅"
"带小孩去玩的" → "亲子 儿童 乐园 博物馆 互动 景点"
```

**技术实现**：

- 调用 OpenAI 兼容 API（支持 DeepSeek / Kimi 双提供者）
- `temperature=0` 保证输出稳定
- `max_tokens=100` 控制输出长度
- 失败时 fallback 到原始 query，不阻塞检索链路

### 2.3 效果验证

| 原始 Query | 改写结果 | 说明 |
|---|---|---|
| "好吃的" | "美食 餐厅 小吃 推荐" | 扩充语义，召回更多美食 |
| "带小孩去玩的" | "亲子 儿童 乐园 景点 互动 游乐场 公园 博物馆" | 提取隐含意图，大幅扩大召回面 |
| "火锅" | "火锅" | 已经是关键词，改写后不变 |

### 2.4 集成点

```
searchSpots(query)
  → rewriteQuery(query)  // LLM 改写
  → embedText(rewrittenQuery)  // 用改写后的关键词做向量检索
  → extractKeywords(query)  // 原始 query 做 LIKE 关键词匹配
```

> **注意**：向量检索用改写后的 query（信号更强），MySQL LIKE 用原始 query（保留用户原词，更精确）。

---

## Phase 3: 多路召回 + RRF 融合

### 3.1 问题分析

**原有做法**：单路 Chroma 向量检索 → 失败降级为 MySQL rating 排序。

**问题**：
- 向量检索擅长语义匹配，但不擅长精确关键词匹配
- MySQL rating 排序没有语义理解，只是按热度排
- 没有融合策略，无法互补两条路径的优势

### 3.2 解决方案：三路并行召回

```
路径 1: Chroma 向量检索（改写后 query，top-20）
       → 语义理解：找到与 query 语义相关的景点

路径 2: MySQL LIKE 关键词检索（原始 query 提取关键词，top-10）
       → 精确匹配：name 或 description 包含关键词的景点

路径 3: MySQL rating 排序（top-10）
       → 热度补充：该城市高评分景点，保证多样性
```

### 3.3 RRF（Reciprocal Rank Fusion）融合

**算法**：对多路召回结果按排名计算融合得分

```
score(doc) = Σ 1 / (rank + K)
```

- `K = 60`（RRF 经典参数）
- 一个文档在多路中出现，得分叠加
- 排名越高，得分越高（rank=1 时 1/61，rank=10 时 1/70）
- 按融合得分排序，去重后取 top-K

**降级策略**：
- Chroma 不可用时：仅用路径 2 + 3
- 任何一路失败：记录日志，不影响其他路

### 3.4 代码结构

```typescript
// src/services/knowledgeService.ts

// 路径 2: MySQL LIKE 关键词检索
async function mysqlKeywordSearch(params) {
  // extractKeywords(query) → 滑动窗口提取 2-5 字词
  // $queryRawUnsafe: SELECT ... WHERE name LIKE "%kw%" OR description LIKE "%kw%"
}

// 路径 3: MySQL rating 排序
async function mysqlRatingSearch(params) {
  // SELECT ... WHERE city = ? ORDER BY rating DESC
}

// RRF 融合
function rrfFuse(path1, path2, path3) {
  // scoreMap: name → { score, item }
  // addPath(items) → 累加每路 1/(rank + 60)
  // sort by rrfScore descending
}
```

---

## Phase 4: Cross-Encoder 重排序

### 4.1 问题分析

RRF 融合后的结果虽然已去重排序，但排序精度有限：
- RRF 仅基于排名，不考虑语义相关性强度
- 一个"火锅"query 召回的 top-5 中，可能混入名字带"火锅"但实际不相关的高评分景点

**需要**：对召回候选做精细重排序。

### 4.2 方案选型

| 方案 | 延迟 | 成本 | 质量 | 可行性 |
|------|------|------|------|--------|
| 本地 Cross-Encoder | +200-500ms | 零 | 优 | ✅ |
| LLM 作为 Reranker | +1000-2000ms | ~$0.002/次 | 优 | ❌ 太慢 |

**选型**：本地 `bge-reranker-base` 模型（~1.2GB）。

### 4.3 技术实现

**模型**：`Xenova/bge-reranker-base`

- Cross-Encoder 架构：输入是 `(query, document)` 对
- 输出是 sigmoid 后的相似度得分 [0, 1]
- 不支持真正的 batch，需逐对评分

**实现文件**：`src/services/reranker.ts`

```typescript
// 核心流程
for (const doc of documents) {
  // 1. Tokenize query + doc pair
  const encoded = await tokenizer(query, {
    text_pair: doc,
    truncation: true,
    return_tensors: false,
  })

  // 2. 通过 SequenceClassification 模型
  const outputs = await model(encoded)

  // 3. logits → sigmoid → score [0, 1]
  const score = sigmoid(Array.from(outputs.logits.data)[0])
}
```

**模型缓存**：tokenizer 和 model 全局单例，首次加载后复用。

**降级**：reranker 失败时回退到 RRF 排序结果。

### 4.4 效果验证

| 文档 | query="火锅" 的 rerank 得分 |
|---|---|
| 喜三嬢老火锅（火锅店） | **90.0%** |
| 饕林餐厅（川菜） | **3.4%** |
| 人民公园 | **0.1%** |

Cross-Encoder 精确区分了"火锅"（菜系）和"火锅"（可能仅出现在名称中的其他场景），将最相关的火锅店排在第一位。

---

## 完整检索链路

```
用户输入："我想吃点辣的"
  │
  ▼
┌──────────────────────────────┐
│ ① Query Rewrite（~300ms）    │
│  "我想吃点辣的"               │
│  → "川菜 湘味 辣味 火锅 餐厅" │
└──────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────┐
│ ② 三路并行召回（~200ms）                │
│                                         │
│  路径 1: Chroma 向量（top-20）          │
│    → embedText("川菜 湘味 辣味...")      │
│    → cosine similarity search           │
│                                         │
│  路径 2: MySQL LIKE（top-10）           │
│    → extractKeywords("我想吃点辣的")     │
│    → name LIKE "%辣%" OR ...            │
│                                         │
│  路径 3: MySQL rating（top-10）         │
│    → WHERE city = '成都'                │
│    → ORDER BY rating DESC               │
└─────────────────────────────────────────┘
  │
  ▼
┌──────────────────────────────┐
│ ③ RRF 融合去重（~1ms）       │
│  score = Σ 1 / (rank + 60)   │
│  top-20 候选送入 reranker    │
└──────────────────────────────┘
  │
  ▼
┌──────────────────────────────┐
│ ④ Cross-Encoder 精排（~200ms）│
│  bge-reranker-base           │
│  query × doc → score [0,1]   │
│  取 top-5                    │
└──────────────────────────────┘
  │
  ▼
输出: 5 条景点信息
  1. 喜三嬢老火锅 [food] 4.4分
     成都 喜三嬢老火锅...
  ---
  2. 饕林餐厅(奎星楼店) [food] 4.5分
     ...
```

### 延迟估算

| 阶段 | 延迟 |
|------|------|
| Query Rewrite（LLM） | 200-400ms |
| 三路召回（并行） | 50-150ms |
| RRF 融合 | <1ms |
| Cross-Encoder 精排 | 200-500ms |
| **总计** | **~500-1000ms** |

### 降级链路

```
Chroma 不可用  → 仅路径 2 + 3
reranker 失败  → 使用 RRF 排序结果
LLM 改写失败   → 使用原始 query
```

---

## 文件清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `src/services/knowledgeService.ts` | **修改** | `createSpot` 多字段拼接、`searchSpots` 三路召回 + RRF + reranker |
| `src/services/queryRewriter.ts` | **新建** | LLM 查询改写服务（支持 DeepSeek / Kimi） |
| `src/services/reranker.ts` | **新建** | Cross-Encoder 重排序（bge-reranker-base） |
| `scripts/re-embed-spreads.ts` | **新建** | 754 条数据重 embedding 迁移脚本 |
| `src/config/embeddings.ts` | **不变** | embedding 配置（reranker 独立管理模型） |
| `src/services/agent/tools/retrieveKnowledge.ts` | **不变** | Agent 工具，直接返回 `searchSpots` 结果字符串 |

---

## 数据准备

### POI 抓取

- **来源**：高德 POI 搜索 API
- **城市**：30 个一二线城市（成都、北京、上海、广州、深圳等）
- **类别**：景点、美食、酒店（各关键词 × 每城 × region 过滤 ≈ 25 POI/类/城）
- **总量**：约 750+ 原始 POI

### POI 转换

- **工具**：`scripts/convert-poi.py`
- **LLM**：DeepSeek API，生成 `description`、`tags`、`rating`、`category`
- **容错**：3 次重试 + JSON 修复 + fallback 基础数据
- **结果**：757 条 Spot（715 条 LLM 生成 + 33 条 fallback）

### 去重

- 原始导入产生重复数据（4226 条）
- 清理后剩 754 条唯一 Spot

---

## 后续优化方向

1. **Phase 5：缓存层** — 对高频 query（如"成都 火锅"）做缓存，减少 LLM 调用和向量检索开销
2. **Phase 6：增量 re-embedding** — 当数据量大到万级时，增量更新 Chroma embedding
3. **Phase 7：评估体系** — 建立 Recall@K / MRR 评估集，量化优化效果
