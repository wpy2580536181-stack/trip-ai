# Trip — AI 智能旅行规划系统

基于 AI 的景点介绍与行程规划系统，用户可输入目的地、预算和天数，AI 自动生成完整的旅行计划，并支持对话式交互。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 + TypeScript + Vite + Vant 4 |
| 后端 | Express 5 + TypeScript |
| 数据库 | MySQL + Prisma ORM + ChromaDB (向量) |
| AI 生成 | LangChain + DeepSeek/Kimi API |
| AI 检索 | bge-small-zh-v1.5 embedding + bge-reranker-base Cross-Encoder (本地) |

## 项目结构

```
trip/
├── trip-front/                  # 前端
│   └── src/
│       ├── api/                 # API 调用层（request.ts + 业务接口）
│       ├── components/          # 通用组件
│       ├── config/              # 前端配置（城市列表等）
│       ├── router/              # 路由配置 + 导航守卫
│       ├── views/               # 页面组件
│       ├── styles/              # 全局样式
│       └── utils/               # 工具函数
│
└── trip-server/                 # 后端
    ├── prisma/                  # 数据库 schema + seed 脚本
    ├── scripts/                 # 数据 pipeline 脚本（POI 抓取、转换、重 embedding）
    └── src/
        ├── config/              # 配置（JWT、数据库、embedding、LLM）
        ├── controllers/         # 控制器（请求处理、参数校验、响应格式化）
        ├── middleware/          # 中间件（认证、鉴权）
        ├── prompts/             # AI Prompt 模板
        ├── routes/              # 路由定义（中间件编排 + 派发到 controller）
        ├── services/            # 业务逻辑层（含 Agent、RAG、reranker）
        └── utils/               # 工具函数
```

## 前置条件

- Node.js >= 18
- MySQL >= 8.0
- ChromaDB（独立进程，见下方）
- 一个兼容 OpenAI 的 LLM API Key（DeepSeek / Kimi）
- 网络连通 HuggingFace（首次启动需下载本地模型约 1.7GB）

## 快速开始

### 1. 克隆并安装依赖

```bash
cd trip-server && npm install
cd ../trip-front && npm install
```

### 2. 配置环境变量

```bash
cp trip-server/.env.example trip-server/.env
```

编辑 `trip-server/.env`，填写实际的数据库连接和 API Key。

### 3. 启动 Chroma

Chroma 是 RAG 向量检索的核心依赖：

```bash
# 方式 1：pip 安装
pip install chromadb
chroma run --path ./trip-server/chroma_data --host 127.0.0.1 --port 8000

# 方式 2：Docker
docker run -d --name chroma -p 8000:8000 \
  -v $(pwd)/trip-server/chroma_data:/chroma/.chroma \
  chromadb/chroma
```

### 4. 初始化数据库

```bash
cd trip-server
npx prisma db push          # 创建数据库表
npm run seed                 # 初始化角色数据（ADMIN/USER）
```

### 5. 导入知识库数据

```bash
cd trip-server
npm run seed:knowledge
```

首次运行会：
1. 下载 bge-small-zh-v1.5 embedding 模型（约 100MB）
2. 从 `data/spots/*.json` 导入 30 个城市的 ~750+ 景点/美食/酒店数据
3. 生成向量存入 ChromaDB

导入成功后输出类似：

```
>>> 导入 chengdu.json (252 个景点)...
   成功: 252, 失败: 0
...
总成功: 754, 总失败: 0
```

### 6. 启动服务

```bash
# 终端 1 — 后端（端口 3000）
cd trip-server && npm run dev

# 终端 2 — 前端（端口 5173）
cd trip-front && npm run dev
```

访问 http://localhost:5173

> **首次启动提示**：后端首次启动时会下载 embedding 和 reranker 本地模型，合计约 1.7GB，需要 2-5 分钟（取决于网络）。后续启动自动复用。

## Performance

> 详细报告：[`docs/performance-benchmark.md`](docs/performance-benchmark.md)
> 原始数据：[`trip-server/docs/performance-data/`](trip-server/docs/performance-data/)

### 关键数字（5 个）

| 指标 | 数值 | 条件 |
|---|---|---|
| 单实例历史 QPS | **6.67** | 10 并发 / GET /api/history/trips |
| SSE 流式 P99 (10 并发) | **47.0s** | 含真实 LLM 调用 + 60% 缓存命中 |
| LLM 缓存命中率 | **40.2%** | 49 个相似 /recommend 请求 |
| LLM /recommend P50 | **29.1s** | 10 个不同 city/days/budgets |
| 单流平均 chunk 数 | **1000+** | 8-50 段 itinerary JSON |

### 压测环境

- 机器：Apple Silicon 10 核 / 16 GB
- Node.js：v26.0.0
- LLM：DeepSeek deepseek-v4-flash
- 压测工具：autocannon + chartjs-node-canvas

### 关键发现

1. **生产 rate limit 工作正常**——登录接口撞 20/min/user 是预期
2. **DeepSeek 上游是容量上限**——conc=20 全失败
3. **Chroma 检索是头号瓶颈**（60% 延迟）—— 加 Redis 缓存 ROI 最高
4. **Cache 命中率 40%**（DeepSeek 自动 prompt cache）—— 可继续优化到 60-70%

> **面试话术**："我的服务在 10 并发下普通 API QPS 达 6.7，SSE 流式 P99 是 47 秒，LLM 缓存命中率 40% 节省约 ¥2/天。瓶颈是 Chroma 向量检索，下一步是加 Redis 缓存层。"

## Architecture

> 详细架构图：[`docs/architecture-diagrams.md`](docs/architecture-diagrams.md)

```
┌──────────────────┐
│   Vue 3 Frontend  │
│   (Vite + Pinia)  │
└────────┬─────────┘
         │ REST + SSE
┌────────▼─────────┐
│  Express 5 API   │
│  (Prisma + Pino) │
└─┬────┬────┬────┬──┘
  │    │    │    │
  ▼    ▼    ▼    ▼
 MySQL Redis Chroma DeepSeek
```

- **前端**：Vue 3 + Vite + Pinia + Element Plus（3055 行）
- **后端**：Express 5 + Prisma + Pino + LangChain（5720 行）
- **存储**：MySQL 8（业务数据）+ Redis 7（缓存/限流/stream）+ Chroma（向量）
- **LLM**：DeepSeek deepseek-v4-flash + bge-small-zh embedding

### 4 大核心能力
1. **AI Agent**：4 工具链（天气/距离/酒店/POI）+ function calling
2. **RAG**：Chroma 向量检索 + 知识库增强 prompt
3. **流式 chat**：SSE + Last-Event-ID 断点续传
4. **评估体系**：10 fixture + 13 evaluator + mock/真实/CI/多采样

## Highlights

4 个面试亮点（4 周前没有的）：

### 1. 断点续传流式 Agent
SSE `Last-Event-ID` 头 + Redis streamStore + 客户端 SSEParser 按 eventId dedup。解决"流到一半断了重传浪费 token"。
详细：[`docs/streamable-agent-resumable.md`](docs/streamable-agent-resumable.md)

### 2. 可视化 Agent 调试
Prisma `AgentStep` 表 + TraceRecorder + admin 三层鉴权 + AdminTrace.vue 时间轴。类似 LangSmith。
详细：[`docs/agent-trace.md`](docs/agent-trace.md)

### 3. 反馈→fixture 自动化闭环
fixtureConverter 纯函数（15 测试）+ feedbackService 3 冲突分支 + Dashboard 按钮 + CLI。用户 👍/👎 直接转评估用例。
详细：[`docs/feedback-to-fixture.md`](docs/feedback-to-fixture.md)

### 4. 生产压测报告
4 场景（HTTP/SSE/LLM/Cache）+ 5 数字 + 6 图表 + Mermaid 架构图。
详细：[`docs/performance-benchmark.md`](docs/performance-benchmark.md)

### 项目讲解文档
4 周亮点组装成面试可讲解文档：1.5-2 小时讲完整个项目，10 个高频问题预演答案。
详细：[`docs/interview-guide.md`](docs/interview-guide.md)

## 上下文管理 & Prompt Cache 设计

> 详细设计文档：[`docs/context-management-improvements.md`](docs/context-management-improvements.md)
> 增量追加 / 分层摘要 / 滑动窗口重构

### 设计动机

DeepSeek / OpenAI / Anthropic 的 **prompt cache 按前缀 token 序列匹配**——前缀任何一字符变化，后面的缓存全废。旧版「滑动窗口」设计每轮都让窗口边界前移，cache 命中率接近 0%，相当于 LLM 每次都全量 prefill。

本项目的目标：**让 prefix 稳定，cache 命中整段历史 + system prompt + summary**。

### 四层上下文结构

```
请求结构（每轮 chat 拼装）：
┌──────────────────────────────────────────────────────────────┐
│ PREFIX（cache 命中区）                                         │
│   ├─ System Prompt            ~500 token，固定不变            │
│   ├─ Conversation.summary     关键决策，append 模式           │
│   └─ Conversation.recap       对话脉络，append 模式           │
├──────────────────────────────────────────────────────────────┤
│ TAIL（cache 必 miss 区，每轮末尾新增 1-2 条）                 │
│   ├─ 所有未压缩的原始消息     单调追加，永不删除              │
│   ├─ Human Message (本轮)                                    │
│   └─ Agent Scratchpad         LangChain 自动管理              │
└──────────────────────────────────────────────────────────────┘
```

### 关键设计：滑动窗口 → 单调追加

| 维度 | 旧版（滑动窗口） | 新版（单调追加） |
|---|---|---|
| 窗口行为 | 取最新 N token，老的掉出 | 所有未压缩消息按时间正序，**不 shift** |
| Cache 命中 | 每轮 prefix 边界前移，~0% 命中 | 每轮只在 TAIL 末尾新增，前面 prefix **继续命中** |
| 旧消息去留 | 从窗口物理消失 | 标 `excludedFromContext=true`，DB 保留 |
| 触发压缩 | 累计 > 8K | 累计 > 16K，**压到 12K** 留 25% buffer |

### 压缩策略

- **触发**：`compressConversation()` 在每轮 `complete`/`error` 事件后**异步**触发
- **判定**：`getContextMessages` 返回 `needsCompaction: boolean`（累计 > 16K 才进 LLM）
- **算法**：`selectCompactionRange` 纯函数（已被 vitest 覆盖）—— 从最老贪心累加 token，凑够需释放量（4K）即停
- **写回**：先 LLM 摘要成功 → 再标 `excludedFromContext=true`（**failure-safe**，LLM 失败时旧消息仍保留在 TAIL，下次重试）
- **频率**：~80 轮一次（窗口 16K 时），cache miss 率 ≈ 1.2%

### 分层摘要（Summary + Recap）

一次 LLM 调用输出两段（`parseLayeredSummary` 解析 + 容错）：

| 字段 | 含义 | 更新策略 |
|---|---|---|
| `Conversation.summary` | 关键决策（目的地/预算/偏好/行程） | append 模式，每次压缩加 `### 追加于 YYYY-MM-DD` 段 |
| `Conversation.recap` | 对话脉络（讨论方向/兴趣演变/未问事项） | append 模式，独立追加 |

降级策略：recap 段解析失败时仍写 summary；summary 段失败时整轮重试，最多 2 次 + 1s/2s 退避；全部失败设 `summaryError=true`，下轮重试。

### DB Schema 变更（本次重构）

```prisma
model Message {
  // ... 原有字段
  excludedFromContext Boolean? @default(false) @map("excluded_from_context")
  @@index([conversationId, excludedFromContext])  // 加速过滤查询
}
```

旧的「滑动窗口 + 全量覆盖摘要」行为已完全移除。

### 调参

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `HISTORY_MAX_TOKENS` | `16000` | TAIL 上限。超过触发压缩；可按 LLM 上下文大小调 |
| （内置常量） | `12000` | 压缩目标 token 数。16K 压到 12K 留 25% buffer |

### 验证

- `tsc --noEmit` 0 错误
- `vitest run src/services/__tests__` 90/90 通过
  - `conversationService.test.ts`（10 个）：覆盖 `getContextMessages` 过滤 excluded、累计 token、needsCompaction 边界
  - `summaryService.test.ts`（7 个）：覆盖 `selectCompactionRange` 贪心算法 + 边界（单条超 target / 整除 / 空数组）

## 环境变量

### 后端（trip-server/.env）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | MySQL 连接字符串 | — |
| `JWT_SECRET` | JWT 签名密钥 | —（必填） |
| `JWT_EXPIRES_IN` | Token 过期时间 | `7d` |
| `PORT` | 服务端口 | `3000` |
| `CORS_ORIGIN` | 允许的前端域名 | `http://localhost:5173` |
| `MODEL_PROVIDER` | AI 模型提供商 | `DEEPSEEK` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | — |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-chat` |
| `KIMI_API_KEY` | Kimi API Key | — |
| `KIMI_BASE_URL` | Kimi API 地址 | `https://api.kimi.cn/v1` |
| `KIMI_MODEL` | Kimi 模型名 | `kimi-for-coding` |
| `CHROMA_URL` | Chroma 向量数据库地址 | `http://localhost:8000` |
| `CHROMA_PERSIST_DIR` | Chroma 数据持久化目录 | `./chroma_data` |
| `HF_ENDPOINT` | HuggingFace 模型下载镜像 | `https://hf-mirror.com/` |
| `HISTORY_MAX_TOKENS` | 对话历史 token 上限（超此值触发压缩） | `16000` |

### 前端（trip-front/.env — 可选）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `VITE_API_TARGET` | API 代理目标地址 | `http://localhost:3000` |

## API 接口

### 健康检查

```
GET /api/test
```

### 用户

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| POST | `/api/user/register` | 注册 | — |
| POST | `/api/user/login` | 登录（支持用户名或邮箱） | — |
| GET  | `/api/user/info` | 获取用户信息 | 需 token |
| PUT  | `/api/user/info` | 更新用户资料 | 需 token |
| PUT  | `/api/user/password` | 修改密码 | 需 token |
| POST | `/api/user/forgot-password` | 获取密码重置验证码 | — |
| POST | `/api/user/reset-password` | 重置密码（需验证码） | — |

### 行程

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/trip/recommend` | AI 生成行程规划 |
| POST | `/api/trip/chat` | AI 对话（SSE 流式响应） |

### 对话 & 历史

| 方法 | 路径 | 说明 | 认证 |
|---|---|---|---|
| GET | `/api/conversations` | 对话列表 | 需 |
| GET | `/api/conversations/:id` | 对话详情 | 需 |
| DELETE | `/api/conversations/:id` | 删除对话 | 需 |
| GET | `/api/history/trips` | 行程历史 | 需 |
| GET | `/api/history/trips/:id` | 行程详情 | 需 |

## 脚本

### trip-server

| 命令 | 说明 |
|---|---|
| `npm run dev` | 开发模式（nodemon + ts-node） |
| `npm run build` | 编译 TypeScript |
| `npm start` | 启动编译后的代码 |
| `npm run seed` | 初始化角色数据 |
| `npm run migrate` | 同步数据库表结构 |
| `npm run seed:knowledge` | 导入知识库数据（30 城 ~750+ 景点） |
| `npx ts-node scripts/re-embed-spreads.ts` | 重 embedding 迁移（更新已有数据的向量） |

### 数据 Pipeline 脚本

| 脚本 | 说明 |
|---|---|
| `scripts/fetch-gaode-poi.ts` | 高德 POI 搜索脚本（30 城 × 3 类，生成原始 POI 数据） |
| `scripts/convert-poi.py` | LLM 转换脚本（POI → Spot，DeepSeek 生成 description/tags/rating） |
| `scripts/convert-poi-to-spots.ts` | TypeScript 版 POI 转换工具 |

## 知识库 RAG

### 知识库概况

- **数据规模**：754 条景点数据，覆盖 30 个一二线城市
- **分类**：景点（attraction）、美食（food）、住宿（hotel）、交通（transport）
- **向量存储**：ChromaDB v1.4.4，cosine similarity，HNSW 索引
- **Embedding 模型**：`bge-small-zh-v1.5`，512 维，本地运行
- **本地模型路径**：`~/.cache/huggingface/hub/`（首次启动自动下载）

### 四层检索链路

```
用户 query → LLM 改写 → 三路并行召回 → RRF 融合 → Cross-Encoder 精排 → 返回 top-K
```

| 层级 | 方案 | 延迟 | 说明 |
|------|------|------|------|
| 1. 查询改写 | DeepSeek/Kimi LLM | 200-400ms | 将自然语言转为检索关键词 |
| 2. 向量召回 | Chroma 向量检索（top-20） | 50-100ms | 语义理解，找到相关景点 |
| 3. 关键词召回 | MySQL LIKE 关键词（top-10） | 5-10ms | 精确名称匹配 |
| 4. 热度召回 | MySQL rating 排序（top-10） | 5-10ms | 补充高评分景点 |
| 5. RRF 融合 | Reciprocal Rank Fusion | <1ms | 三路去重融合，候选送入精排 |
| 6. Cross-Encoder | bge-reranker-base | 200-500ms | 对 top-20 候选做精细重排序 |
| **总计** | | **~500-1000ms** | |

### RRF 融合算法

```
score(doc) = Σ 1 / (rank + K)
```

K = 60，对多路召回结果按排名累加融合得分，排名越高得分越高。一个文档在多路中出现时得分叠加。

### Cross-Encoder 重排序

对 RRF 融合后的 top-20 候选，使用 `bge-reranker-base` Cross-Encoder 模型逐对计算 query-doc 相关性得分（sigmoid → [0,1]），取 top-K 返回。

### 降级链路

```
Chroma 不可用  → 仅用 MySQL LIKE + rating 双路
reranker 失败  → 使用 RRF 排序结果
LLM 改写失败   → 使用原始 query
```

### 详细文档

完整的四层优化实施文档（索引层、查询改写、多路召回、重排序）见：[RAG_OPTIMIZATION.md](docs/RAG_OPTIMIZATION.md)

## 安全说明

- JWT Secret 必须通过 `JWT_SECRET` 环境变量设置，无硬编码 fallback
- 密码重置使用 UUID token，30 分钟有效，单次使用
- 登录、注册、密码重置接口均有频率限制（15 分钟 10 次）
- `.env` 文件已被 `.gitignore` 排除，请勿提交真实密钥
