# 架构图 (Architecture Diagrams)

> 4 张 Mermaid 图，覆盖系统架构、Agent 时序、上下文数据流、评估体系。
> GitHub 原生渲染，源码即真相 (Source of Truth)。

---

## 1. 系统架构图 (System Architecture)

```mermaid
flowchart TB
    FE["Frontend<br/>Vue 3 + Vite + Pinia + Element Plus"]
    BE["Backend<br/>Express 5 + Prisma + Pino"]
    DB[("MySQL 8<br/>(via Prisma)")]
    RD[("Redis 7<br/>streamStore · rate limit · stats")]
    VC[("Chroma<br/>Vector DB")]
    LLM["DeepSeek<br/>deepseek-v4-flash"]
    EMB["bge-small-zh<br/>Embedding"]

    FE -->|HTTPS REST + SSE| BE
    BE -->|Prisma ORM| DB
    BE -->|ioredis| RD
    BE -->|vector search| VC
    BE -->|chat completion| LLM
    BE -->|embed via LangChain| EMB
```

---

## 2. Agent 执行时序 (Agent Execution Sequence)

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Frontend
    participant BE as tripService
    participant AE as AgentEngine
    participant L as LLM (DeepSeek)
    participant T as Tool
    participant DB as MySQL

    U->>FE: send message
    FE->>BE: POST /api/trip/chat (SSE)
    BE->>DB: pre-create empty assistant msg
    BE->>AE: chat({userId, messageId, signal, onEvent})
    AE->>L: invoke(messages + tools)
    L-->>AE: tool_call {name, args}
    AE->>T: execute(args)
    T-->>AE: result
    AE-->>BE: on_tool_start / on_tool_end
    AE->>L: invoke(messages + tool result)
    L-->>AE: content chunks
    AE-->>BE: on_chunk (SSE)
    BE-->>FE: data: {type:'chunk'}
    AE-->>BE: on_complete (with usage)
    BE->>DB: persist assistant message
    BE-->>FE: data: {type:'complete', reply, usage}
```

---

## 3. 上下文管理数据流 (Context Management Data Flow)

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

## 4. 评估体系 (Evaluation System)

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

    FX --> EN --> RUN
    RUN --> MD --> EV
    EV <--> LLM
    EV --> OUT
    OUT -->|negative| FB
    FB -->|append| FX
```
