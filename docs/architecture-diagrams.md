# 架构图 (Architecture Diagrams)

> 5 张 Mermaid 图，覆盖系统架构、Agent 时序、RAG 检索、上下文数据流、评估体系。
> GitHub 原生渲染，源码即真相 (Source of Truth)。

---

## 1. 系统架构图 (System Architecture)

```mermaid
flowchart TB
    FE["Frontend<br/>Vue 3 + Vite + Pinia + Element Plus"]
    BE["Backend<br/>Express 5 + Prisma + Pino"]
    DB[("MySQL 8<br/>(via Prisma)")]
    RD[("Redis 7<br/>streamStore · rate limit · stats")]
    VC[("Chroma<br/>Vector Index<br/>30k POI embeddings")]
    LLM["DeepSeek<br/>deepseek-v4-flash"]
    EMB["bge-small-zh<br/>Embedding<br/>(local, 512d)"]
    RERANK["bge-reranker-base<br/>Cross-Encoder<br/>(local, top-20)"]
    AGENT["AgentEngine<br/>LangGraph<br/>research + plan + chat"]
    RAG["KnowledgeService<br/>3-path recall +<br/>RRF + rerank"]
    REWRITER["QueryRewriter<br/>本地关键词提取<br/>(~1ms, 替代 LLM)"]
    MCP_PROC["Amap McpProcess<br/>stdio 子进程"]
    MCP_CLIENT["Amap McpClient<br/>JSON-RPC +<br/>Guard Layer"]
    UPL["Unsplash ImageFetcher<br/>batch fetch +<br/>30d LRU cache"]
    MAPS["Amap MCP Tools<br/>maps_weather · maps_text_search<br/>maps_around · maps_…… (12 tools)"]
    POI("高德 POI 图片<br/>(maps_text_search)")
    US("Unsplash API<br/>(fallback)")

    FE -->|HTTPS REST + SSE| BE
    BE -->|Prisma ORM| DB
    BE -->|ioredis| RD
    BE --> AGENT
    AGENT --> RAG
    RAG --> REWRITER
    RAG -->|vector search top-20| VC
    RAG -->|keyword LIKE top-10| DB
    RAG -->|rating top-10| DB
    RAG -->|rerank top-5| RERANK
    AGENT -->|embeddings| EMB
    AGENT -->|chat completion| LLM
    AGENT -->|call tool| MCP_CLIENT
    MCP_CLIENT -->|spawn + stdio| MCP_PROC
    MCP_PROC -->|tools/list · tools/call| MAPS
    BE -->|行程完成→后端 batch| UPL
    UPL -->|首选| POI
    UPL -->|fallback| US
```

---

## 2. Agent 执行时序 (Agent Execution Sequence)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as tripService
    participant AE as AgentEngine
    participant RAG as KnowledgeService
    participant RR as Rewriter
    participant MCP as Amap MCP
    participant L as LLM (DeepSeek)
    participant DB as MySQL / Chroma
    participant IMG as ImageFetcher

    U->>FE: send message
    FE->>BE: POST /api/trip/chat (SSE)
    BE->>DB: pre-create empty assistant msg
    BE->>AE: chat({userId, messageId, signal, onEvent})
    AE->>RAG: research(query, city)
    RAG->>RR: rewriteQuery (local keywords ~1ms)
    RR-->>RAG: rewritten
    RAG->>DB: 3-path recall (vector + LIKE + rating)
    DB-->>RAG: 40 candidates
    RAG->>RAG: RRF fusion → top-20
    RAG->>RAG: Cross-Encoder rerank → top-5
    RAG-->>AE: results
    AE->>L: invoke(messages + tools)
    L-->>AE: tool_call maps_weather / maps_text_search
    AE->>MCP: callTool(name, args)
    MCP-->>AE: result
    AE->>L: invoke(messages + result)
    L-->>AE: content chunks
    AE-->>BE: on_chunk (SSE)
    BE-->>FE: data: {type:'chunk'}
    AE-->>BE: on_complete (with usage)
    BE->>DB: persist assistant message
    BE-->>FE: data: {type:'complete', reply, usage}
    Note over BE,IMG: 回复后 batch 拉图（Amap POI → Unsplash）
    BE->>IMG: fetchImages(itinerary)
    IMG-->>BE: urls → trip.itinerary JSON
    BE->>DB: update trip.itinerary
```

---

## 3. RAG 检索链路 (RAG Retrieval Pipeline)

```mermaid
flowchart LR
    Q["用户查询<br/>eg. 看夜景最好的地方"] --> RW["QueryRewriter<br/>本地关键词提取<br/>→ 广州 夜景 看夜景 珠江"]
    RW --> PATH1["Chroma 向量检索<br/>top-20<br/>语义相似度"]
    RW --> PATH2["MySQL LIKE 关键词<br/>top-10<br/>精确匹配"]
    RW --> PATH3["MySQL rating 排序<br/>top-10<br/>热度兜底"]
    PATH1 & PATH2 & PATH3 --> RRF["RRF 融合<br/>top-20"]
    RRF --> CE{"Cross-Encoder<br/>重排"}
    CE -->|RRF 得分 >0.15| SKIP["跳过重排<br/>直接 top-5"]
    CE -->|否则| RERANK["bge-reranker-base<br/>top-20 → top-5"]
    SKIP --> OUT["最终结果<br/>5 条 POI"]
    RERANK --> OUT
```

---

## 4. 上下文管理数据流 (Context Management Data Flow)

```mermaid
flowchart LR
    UM[User message] --> HIST[Message history<br/>MySQL]
    HIST --> TC[Token counter<br/>current usage]
    TC --> BUDGET{Token budget<br/>HISTORY_MAX_TOKENS=8000}
    BUDGET -->|within| KEEP[Keep all messages]
    BUDGET -->|approaching| SUMM[Summarize old msgs]
    BUDGET -->|exceeded| CMP[Compressor<br/>compressConversation]
    SUMM --> SC[Summary cache<br/>in-memory]
    SC --> CMP
    CMP --> LLM[LLM call<br/>compressed context]
    KEEP --> LLM
```

---

## 5. 评估体系 (Evaluation System)

```mermaid
flowchart TB
    FX["Fixtures<br/>fixtures/*.yaml +<br/>fixtures/generated/*.yaml"]
    EN["CLI / API entry<br/>(eval / evalApi)"]
    RUN[Runner]
    MD["4 Modes<br/>mock · real · multi-sample · report"]
    EV["13 Evaluators<br/>must_contain_keywords · must_not ·<br/>regex · json_schema · ..."]
    LLM["LLM<br/>(mock or real)"]
    OUT["Output<br/>JSON report · HTML report · score"]
    FB["Feedback Loop<br/>negative feedback →<br/>fixtureConverter → new YAML"]
    QCHK["Quality Check<br/>check-rag-quality.ts<br/>6 scenarios · top-3 match vs ideal"]

    FX --> EN --> RUN
    RUN --> MD --> EV
    EV <--> LLM
    EV --> OUT
    OUT -->|negative| FB
    FB -->|append| FX
    QCHK -.->|参考| EV
```
