# Trip 对话持久化 — 技术设计文档（TDD）

> **文档状态**：草案 v1.0  
> **日期**：2026-08-01  
> **对应 PRD**：`docs/trip-conversation-persistence-prd.md`  
> **下游消费者**：前端（trip-front）、后端（trip-backend）

---

## 0. 精读实现后的关键发现

### 0.1 后端实际状态

| 发现 | 位置 | 说明 |
|---|---|---|
| **`Conversation` 表无 `trip_id`** | `src/models/conversation.py:9-66` | 只有 `user_id/title/summary/recap/summary_error/summary_at` |
| **`ChatRequest` 已有 `trip_id`** | `src/schemas/trip.py:24-39` | 但仅用于 `_build_trip_context()` 注入行程上下文，**不持久化** |
| **`_get_or_create_conversation` 不处理 `trip_id`** | `src/services/trip_service.py:30-51` | 创建新对话时写 `title="新对话"`，`trip_id` 未传入 |
| **`conversation_service.create_conversation` 不处理 `trip_id`** | `src/services/conversation_service.py:267-294` | 只写 `user_id/title/summary/summary_error/summary_at` |
| **`history_service.delete_trip` 注释称 cascade 会删 conversations** | `src/services/history_service.py:181` | 但 `trips` 与 `conversations` 之间**无数据库外键**，该注释不实 |
| **无 Alembic 迁移工具** | `pyproject.toml` 含 `alembic>=1.13.0` 但未配置 | 当前用 `Base.metadata.create_all`（`create_tables.py`）建表 |
| **SSE complete 已返回 `conversationId`** | `src/services/trip_service.py:284-287` | 前端 ChatPanel/Chat.vue 已消费并写 localStorage |

### 0.2 前端实际状态

| 发现 | 位置 | 说明 |
|---|---|---|
| **ChatPanel 按 tripId 隔离** | `src/components/ChatPanel.vue:73` | `trip_panel_conv_${tripId}`，watch `props.tripId` 迁移 key |
| **Chat.vue 全局单 key** | `src/views/Chat.vue:30` | `trip_chat_conversation_id`，与 tripId 无绑定 |
| **Chat.vue 有 `activeTripId`** | `src/views/Chat.vue:84-85` | 从 `route.query.tripId` 读取，但不查找已有对话 |
| **Chat.vue 选择历史会话时清空 `activeTripId`** | `src/views/Chat.vue:265-266` | `activeTripId.value = null`，切断与行程关联 |
| **Detail.vue 嵌入 ChatPanel** | `src/views/Detail.vue:448-451` | `:trip-id="currentTripMeta?.id"`，路由切换重挂载 |
| **两套 localStorage 完全不互通** | ChatPanel `trip_panel_conv_*` vs Chat `trip_chat_conversation_id` | 核心不 consistency 根因 |

### 0.3 数据模型现状

```sql
-- 当前 conversations 表结构（从 SQLAlchemy 模型推导）
CREATE TABLE conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(100),
    summary TEXT,
    recap TEXT,
    summary_error BOOLEAN DEFAULT FALSE,
    summary_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
    -- ⚠️ 无 trip_id
);

-- trips 表结构
CREATE TABLE trips (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    from_city VARCHAR(50),
    city VARCHAR(50) NOT NULL,
    days INTEGER NOT NULL,
    budget INTEGER NOT NULL,
    content JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'completed',
    parent_trip_id INTEGER REFERENCES trips(id)  -- 自引用版本链
);
```

---

## 1. 方案对比

### 方案 A：`conversations` 表新增 `trip_id` 字段（**推荐**）

#### 改动映射

| 层级 | 改动 | 文件 |
|---|---|---|
| **DB 模型** | `Conversation` 新增 `trip_id = Column(Integer, ForeignKey("trips.id"), nullable=True, index=True)` | `src/models/conversation.py` |
| **DB 建表** | 修改 `create_tables.py`（`create_all` 自动 pickup）或手动 `ALTER TABLE` | `create_tables.py` |
| **后端 Schema** | `ConversationResponse` 新增 `tripId` 字段 | `src/schemas/conversation.py` |
| **后端 Service** | `_get_or_create_conversation` 接收 `trip_id`，新建时写入 | `src/services/trip_service.py` |
| **后端 Service** | `ConversationService.create_conversation` 接收 `trip_id` | `src/services/conversation_service.py` |
| **后端 Controller** | 新增 `GET /api/trips/{tripId}/conversation` | `src/controllers/conversation_controller.py` |
| **后端 Service** | 新增 `ConversationService.get_by_trip_id()` | `src/services/conversation_service.py` |
| **前端 API** | 新增 `getConversationByTripId(tripId)` | `trip-front/src/api/conversation.ts` |
| **前端 Chat.vue** | 挂载时若 URL 带 `tripId`，调新接口查找已有对话 | `src/views/Chat.vue` |
| **前端 ChatPanel.vue** | 保留现有 `trip_panel_conv_${tripId}` 策略 | 无需改动 |

#### 关键代码路径

```
用户打开 /chat?tripId=123
        │
        ▼
  Chat.vue onMounted
        │
        ├─ 读取 route.query.tripId = 123
        ├─ 读取 localStorage['trip_chat_conversation_id']（可选 fallback）
        │
        ├─ 调用 GET /api/trips/123/conversation
        │   │
        │   ▼
        │  ConversationService.get_by_trip_id(db, 123)
        │   │
        │   ├─ 查库: SELECT * FROM conversations WHERE trip_id = 123 AND user_id = ? LIMIT 1
        │   │
        │   ├─ 有记录 → 返回 { conversationId: 456 }
        │   └─ 无记录 → 返回 404
        │
        ├─ 404 → currentConversationId = null（走正常新建流程）
        └─ 200 → currentConversationId = 456，加载历史消息
```

#### 优点

| 优点 | 说明 |
|---|---|
| **简单直接** | 单字段外键，SQL 原生支持 `JOIN` 和 `WHERE trip_id = ?` |
| **性能最优** | `trip_id` 建索引后，按行程查对话 O(log N) |
| **ORM 友好** | SQLAlchemy relationship 可直接加 `Conversation.trip = relationship("Trip")` |
| **向后兼容** | `nullable=True`，存量对话 `trip_id = NULL`，不影响现有功能 |
| **SSE 流式不变** | `chat_stream` 接收 `trip_id` 后，在 `_get_or_create_conversation` 时一起写入 |

#### 缺点

| 缺点 | 说明 |
|---|---|
| **迁移需手动 ALTER TABLE** | 无 Alembic，需写 `ALTER TABLE conversations ADD COLUMN trip_id` |
| **一行程一对话硬编码** | 未来若支持同一行程多个对话，需改关联表 |

---

### 方案 B：新增 `trip_conversations` 关联表

#### 改动映射

| 层级 | 改动 | 文件 |
|---|---|---|
| **新模型** | `TripConversation(Base, BaseModel)` — `trip_id + conversation_id` 联合主键 | `src/models/trip_conversation.py` |
| **后端 Service** | 新增 `ConversationService.get_by_trip_id()` | `src/services/conversation_service.py` |
| **后端 Controller** | 新增 `GET /api/trips/{tripId}/conversation` | `src/controllers/conversation_controller.py` |
| **前端** | 同方案 A | 同方案 A |

#### 优点

| 优点 | 说明 |
|---|---|
| **支持一对多** | 同一行程可关联多个对话（未来可扩展） |
| **无外键约束** | 删除对话不影响行程，删除行程需手动清理关联表 |

#### 缺点

| 缺点 | 说明 |
|---|---|
| **过度设计** | PRD 明确 NG1："不支持一个行程对应多个对话" |
| **查询复杂** | 需 `JOIN trip_conversations ON conversations.id = trip_conversations.conversation_id` |
| **联合主键维护成本** | 插入/删除需同时操作两张表 |

---

### 方案 C：纯前端 localStorage 统一 + 后端无感知

#### 改动映射

| 层级 | 改动 | 文件 |
|---|---|---|
| **前端** | ChatPanel 与 Chat.vue 统一用 `trip_panel_conv_${tripId}` | `ChatPanel.vue` + `Chat.vue` |
| **前端** | Chat.vue 从 `route.query.tripId` 读取，查找对应 key | `Chat.vue` |
| **后端** | 零改动 | — |

#### 优点

| 优点 | 说明 |
|---|---|
| **后端零改动** | 不涉及数据库 schema 和 service 层 |
| **实现最快** | 只改前端两个组件 |

#### 缺点

| 缺点 | 说明 |
|---|---|
| **localStorage 清空即丢失** | PRD 中 AC8 明确要求"后端仍可通过 `trip_id` 查找到对话" |
| **多端不同步** | localStorage 是单设备单浏览器 |
| **历史会话无行程关联** | 用户在 `/chat` 选择历史会话时，`activeTripId` 被清空 |
| **非权威来源** | PRD 风险 R2："前端 localStorage 与后端数据库不一致" |

---

## 2. 推荐方案与理由

### 推荐：**方案 A**

| 维度 | 方案 A | 方案 B | 方案 C |
|---|---|---|---|
| **实现复杂度** | 中 | 高 | 低 |
| **后端改动量** | 中（6 文件） | 高（+1 模型） | 零 |
| **数据一致性** | 高（数据库权威） | 高 | 低 |
| **扩展性** | 中 | 高 | 低 |
| **是否满足 AC8** | ✅ | ✅ | ❌ |
| **是否满足 PRD G3** | ✅ | ✅ | ❌ |

**核心理由**：

1. **方案 A 是"够用且最简"** — PRD 明确 NG1 不支持多对话，方案 B 的关联表是过度工程。
2. **方案 C 无法解决 localStorage 清空后的对话丢失** — AC8 要求后端兜底。
3. **方案 A 与现有代码风格一致** — `Conversation.user_id` 已经是外键模式，加 `trip_id` 是同一范式。
4. **SSE 流式完全不变** — `chat_stream` 的 `trip_id` 参数已有，只需在 `_get_or_create_conversation` 中透传写入。

---

## 3. 方案 A 详细设计

### 3.1 数据模型改动

```python
# src/models/conversation.py — 新增字段

class Conversation(Base, BaseModel):
    # ... 现有字段 ...
    
    trip_id = Column(
        Integer,
        ForeignKey("trips.id"),
        nullable=True,
        index=True,
        comment="关联行程ID（可空，存量对话为 NULL）"
    )
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    trip = relationship("Trip", back_populates="conversations")  # 新增
    messages = relationship(...)
    token_logs = relationship(...)
```

```python
# src/models/trip.py — 补充反向关系

class Trip(Base, BaseModelWithoutUpdatedAt):
    # ... 现有字段 ...
    
    conversations = relationship(
        "Conversation",
        back_populates="trip",
        cascade="all, delete-orphan"  # 删除行程时级联清空关联（非删除对话）
    )
```

> **注意**：`cascade="all, delete-orphan"` 在 `Trip.conversations` 上表示"删除行程时，将关联对话的 `trip_id` 设为 NULL"，而非删除对话本身。这符合 PRD 中"删除行程后关联对话成为孤儿"的风险容忍。

### 3.2 数据库迁移

由于无 Alembic，采用 **手动 ALTER TABLE**：

```sql
-- migrations/001_add_trip_id_to_conversations.sql

-- 1. 加字段（可空）
ALTER TABLE conversations 
    ADD COLUMN trip_id INTEGER;

-- 2. 加外键（ trips.id ）
ALTER TABLE conversations 
    ADD CONSTRAINT fk_conversations_trip_id 
    FOREIGN KEY (trip_id) REFERENCES trips(id) 
    ON DELETE SET NULL;

-- 3. 加索引
CREATE INDEX idx_conversations_trip_id 
    ON conversations(trip_id);

-- 4. 验证
SELECT column_name, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'conversations' 
  AND column_name = 'trip_id';
```

迁移执行方式（FastAPI startup）：

```python
# src/config/database.py — init_db() 末尾追加

async def init_db():
    # ... 现有逻辑 ...
    
    # 执行 pending migrations
    from src.utils.migrations import run_pending_migrations
    await run_pending_migrations(conn)
```

```python
# src/utils/migrations.py — 新建

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"
_APPLIED_TABLE = "schema_migrations"

async def run_pending_migrations(conn):
    """执行未应用的 migration（幂等）"""
    # 1. 确保 schema_migrations 表存在
    await conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {_APPLIED_TABLE} (
            filename VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    
    # 2. 找出已应用的
    result = await conn.execute(text(f"SELECT filename FROM {_APPLIED_TABLE}"))
    applied = {row[0] for row in result.fetchall()}
    
    # 3. 按序执行未应用的
    migration_files = sorted(_MIGRATIONS_DIR.glob("*.sql"))
    for f in migration_files:
        if f.name in applied:
            continue
        sql = f.read_text()
        await conn.execute(text(sql))
        await conn.execute(text(f"INSERT INTO {_APPLIED_TABLE} (filename) VALUES ('{f.name}')"))
        logger.info(f"Migration applied: {f.name}")
```

### 3.3 后端接口改动

#### 新增 `GET /api/trips/{tripId}/conversation`

```python
# src/controllers/conversation_controller.py

@router.get(
    "/by-trip/{trip_id}",
    response_model=dict,
    summary="按行程查找关联对话",
    description="""
    查找指定行程的最新关联对话（含消息）。
    
    路径参数：
    - trip_id: 行程 ID
    
    返回对话详情和消息列表。
    
    错误响应：
    - 401: 未授权
    - 404: 行程无关联对话
    """
)
async def get_conversation_by_trip(
    trip_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    conversation = await ConversationService.get_by_trip_id(
        db, trip_id, current_user.id
    )
    
    # 复用现有序列化逻辑
    conversation_dict = {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "trip_id": conversation.trip_id,
        "title": conversation.title,
        "summary": conversation.summary,
        "summary_error": conversation.summary_error,
        "summary_at": conversation.summary_at,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            }
            for msg in conversation.messages
        ]
    }
    
    return {
        "code": 200,
        "data": conversation_dict,
        "message": "获取行程对话成功",
        "error": None
    }
```

```python
# src/services/conversation_service.py

@staticmethod
async def get_by_trip_id(
    db: AsyncSession,
    trip_id: int,
    user_id: int
) -> Conversation:
    """按行程 ID 查找最新关联对话（含消息）
    
    查找逻辑：
    1. 验证行程存在且属于该用户（防止 ID 遍历）
    2. 查找 trip_id = ? 的最新对话（按 updated_at DESC）
    3. 预加载消息（selectinload）
    
    Raises:
        NotFoundException: 行程不存在或无关联对话
    """
    # 1. 验证行程存在（可复用 HistoryService.get_trip）
    from src.services.history_service import HistoryService
    await HistoryService.get_trip(db, trip_id, user_id)
    
    # 2. 查找最新关联对话
    result = await db.execute(
        select(Conversation)
        .where(
            Conversation.trip_id == trip_id,
            Conversation.user_id == user_id
        )
        .options(selectinload(Conversation.messages))
        .order_by(Conversation.updated_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    
    if not conversation:
        raise NotFoundException("行程关联对话")
    
    return conversation
```

#### 修改 `_get_or_create_conversation` 透传 `trip_id`

```python
# src/services/trip_service.py

async def _get_or_create_conversation(
    user_id: int,
    conversation_id: Optional[int],
    trip_id: Optional[int] = None,  # 新增
) -> Conversation:
    """获取或创建对话。"""
    async with async_session() as session:
        if conversation_id:
            result = await session.execute(
                select(Conversation).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            conv = result.scalar_one_or_none()
            if conv:
                # 若对话无 trip_id 但本次请求携带 trip_id，回写关联
                if conv.trip_id is None and trip_id is not None:
                    conv.trip_id = trip_id
                    await session.commit()
                    await session.refresh(conv)
                return conv
        # 创建新对话
        conv = Conversation(
            user_id=user_id, 
            title="新对话",
            trip_id=trip_id,  # 新增
        )
        session.add(conv)
        await session.commit()
        await session.refresh(conv)
        return conv
```

#### 修改 `chat_stream` 透传 `trip_id`

```python
# src/services/trip_service.py — chat_stream 第 124 行

conversation = await _get_or_create_conversation(
    user_id, 
    conversation_id,
    trip_id=trip_id,  # 新增
)
```

### 3.4 前端改动

#### 新增 `getConversationByTripId`

```typescript
// trip-front/src/api/conversation.ts

export interface ConversationByTripResponse {
  id: number
  userId: number
  tripId: number
  title: string | null
  summary: string | null
  messages: ConversationDetailMessage[]
  createdAt: string
  updatedAt: string
}

export async function getConversationByTripId(tripId: number) {
  return get<ConversationByTripResponse>(`conversations/by-trip/${tripId}`)
}
```

#### 修改 `Chat.vue` 按 tripId 查找已有对话

```typescript
// src/views/Chat.vue — onMounted 逻辑

onMounted(async () => {
  // 现有逻辑：初始化 currentConversationId
  const stored = typeof window !== 'undefined' ? localStorage.getItem(CONVERSATION_ID_KEY) : null
  const parsedStored = stored ? Number(stored) : NaN
  currentConversationId.value = Number.isInteger(parsedStored) ? parsedStored : null

  // 新增：若 URL 带 tripId，优先按行程查找已有对话
  const tripIdFromQuery = Number(route.query.tripId)
  if (Number.isInteger(tripIdFromQuery) && tripIdFromQuery > 0 && !currentConversationId.value) {
    try {
      const res = await getConversationByTripId(tripIdFromQuery)
      const conv = res.data
      if (conv?.id) {
        currentConversationId.value = conv.id
        localStorage.setItem(CONVERSATION_ID_KEY, String(conv.id))
        // 加载历史消息
        messages.value = (conv.messages || []).map(m => ({
          id: m.id,
          role: m.role === 'user' ? 'user' : 'ai',
          content: m.content,
          timestamp: m.createdAt,
        }))
      }
    } catch (e) {
      // 404（行程无对话）或 500 都降级为空对话，不阻断
      if ((e as any)?.response?.status !== 404) {
        handleApiError(e, message)
      }
    }
  }

  loadConversations()
})
```

#### ChatPanel.vue — 保留现有策略

`ChatPanel.vue` 已有完整的按 tripId 持久化逻辑（`trip_panel_conv_${tripId}` + `restoreConversation` + `watch props.tripId` 迁移），**无需改动**。

### 3.5 改动范围总览

| 文件 | 改动类型 | 行数估算 |
|---|---|---|
| `src/models/conversation.py` | 新增 `trip_id` + relationship | +8 |
| `src/models/trip.py` | 新增 `conversations` relationship | +5 |
| `migrations/001_add_trip_id_to_conversations.sql` | 新建 | +15 |
| `src/utils/migrations.py` | 新建 | +60 |
| `src/services/conversation_service.py` | 新增 `get_by_trip_id` | +35 |
| `src/services/trip_service.py` | 修改 `_get_or_create_conversation` + `chat_stream` | +10 |
| `src/controllers/conversation_controller.py` | 新增 `GET /conversations/by-trip/{trip_id}` | +60 |
| `src/schemas/conversation.py` | `ConversationResponse` 新增 `tripId` | +3 |
| `trip-front/src/api/conversation.ts` | 新增 `getConversationByTripId` | +10 |
| `trip-front/src/views/Chat.vue` | onMounted 增加按 tripId 查找逻辑 | +30 |
| **合计** | | **~230** |

---

## 4. 接口契约

### 4.1 新增 `GET /api/conversations/by-trip/{tripId}`

**请求**：

```
GET /api/conversations/by-trip/123
Authorization: Bearer <token>
```

**响应 200**：

```json
{
  "code": 200,
  "data": {
    "id": 456,
    "user_id": 1,
    "trip_id": 123,
    "title": "北京三日游规划",
    "summary": "用户计划北京三日游...",
    "summary_error": false,
    "summary_at": "2026-08-01T12:00:00Z",
    "created_at": "2026-08-01T10:00:00Z",
    "updated_at": "2026-08-01T12:00:00Z",
    "messages": [
      {
        "id": 1,
        "role": "user",
        "content": "帮我规划北京三日游",
        "created_at": "2026-08-01T10:00:01Z"
      },
      {
        "id": 2,
        "role": "assistant",
        "content": "好的，我来为您规划...",
        "created_at": "2026-08-01T10:00:05Z"
      }
    ]
  },
  "message": "获取行程对话成功",
  "error": null
}
```

**响应 404**：

```json
{
  "code": 404,
  "data": null,
  "message": "行程无关联对话",
  "error": "NOT_FOUND"
}
```

**响应 401**：

```
HTTP/1.1 401 Unauthorized
```

---

## 5. 验收标准（技术层面）

### 5.1 后端验收

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T-AC1** | `Conversation` 模型新增 `trip_id` 字段 | `conversations` 表有 `trip_id` 列，可空，有索引 |
| **T-AC2** | 新建对话时传入 `trip_id` | `conversations.trip_id` 写入对应值 |
| **T-AC3** | 复用已有对话时传入 `trip_id`（对话原 `trip_id` 为 NULL） | 回写 `trip_id` |
| **T-AC4** | `GET /api/conversations/by-trip/{tripId}` 返回关联对话 | 200 + 对话详情 + 消息 |
| **T-AC5** | `GET /api/conversations/by-trip/{tripId}` 无关联对话 | 404 |
| **T-AC6** | `GET /api/conversations/by-trip/{tripId}` 访问他人行程 | 404（HistoryService 验证权限） |
| **T-AC7** | 删除行程时关联对话 | `trip_id` 设为 NULL，对话不删除 |

### 5.2 前端验收

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T-AC8** | `Chat.vue` 打开 `/chat?tripId=123`（有对话） | 加载已有对话历史 |
| **T-AC9** | `Chat.vue` 打开 `/chat?tripId=123`（无对话） | 空对话，发送后创建并关联 |
| **T-AC10** | `Chat.vue` 打开 `/chat`（无 tripId） | 原有行为不变 |
| **T-AC11** | `ChatPanel.vue` 刷新 `/detail?id=123` | 恢复已有对话（现有逻辑） |
| **T-AC12** | `Chat.vue` 与 `ChatPanel.vue` 对同一行程发送消息 | 消息追加到同一 `conversationId` |

---

## 6. 风险清单（技术层面）

| 编号 | 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|---|
| **TR1** | **手动 ALTER TABLE 失败**（锁表/权限） | 中 | 高 | 在低峰期执行；先 `ALTER TABLE ... ADD COLUMN` 再 `CREATE INDEX CONCURRENTLY` |
| **TR2** | **`create_tables.py` 被重新执行时覆盖** | 低 | 中 | `create_all` 对已有列友好（`ADD COLUMN IF NOT EXISTS` 需手动写） |
| **TR3** | **前端 `Chat.vue` onMounted 竞态** | 中 | 低 | `getConversationByTripId` 失败时降级为空对话 |
| **TR4** | **删除行程时级联逻辑不预期** | 低 | 低 | `ON DELETE SET NULL` 确保对话不丢失 |
| **TR5** | **存量对话 `trip_id = NULL` 被误判** | 低 | 低 | 新接口 `get_by_trip_id` 查 `trip_id = ?`，NULL 值自然过滤 |

---

## 7. 替代方案：若不想改数据库 schema

若团队对 `ALTER TABLE` 有顾虑，可采用**过渡方案**：

**过渡方案：`trip_chat_mapping` 单独表（轻量关联）**

```sql
CREATE TABLE IF NOT EXISTS trip_chat_mapping (
    trip_id INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (trip_id, user_id)  -- 一行程一用户一对话
);
```

优点：
- 不修改 `conversations` 表结构
- 可独立清理

缺点：
- 插入对话时需双写（`conversations` + `trip_chat_mapping`）
- 查询需 JOIN
- 与方案 A 比无实质优势，仅心理上"不改现有表"

**建议**：直接方案 A，过渡方案没必要。

---

## 8. 实施顺序建议

```
Phase 1: 后端数据层（1-2 天）
  ├─ T1: migrations/001 + src/utils/migrations.py
  ├─ T2: src/models/conversation.py + src/models/trip.py
  └─ T3: 手动执行 ALTER TABLE

Phase 2: 后端接口层（1 天）
  ├─ T4: src/schemas/conversation.py（新增 tripId）
  ├─ T5: src/services/conversation_service.py（新增 get_by_trip_id）
  ├─ T6: src/controllers/conversation_controller.py（新增 by-trip 端点）
  └─ T7: src/services/trip_service.py（_get_or_create_conversation 透传）

Phase 3: 前端接入层（0.5 天）
  ├─ T8: trip-front/src/api/conversation.ts
  └─ T9: src/views/Chat.vue onMounted 增加按 tripId 查找

Phase 4: 验证（0.5 天）
  ├─ T10: 后端测试（ConversationService.get_by_trip_id + controller）
  ├─ T11: 前端手动验证（Chat.vue ↔ ChatPanel.vue）
  └─ T12: PRD 验收标准全量回归
```

---

## 9. 待决策项

| 编号 | 决策 | 选项 | 推荐 |
|---|---|---|---|
| **D1** | `get_by_trip_id` 返回哪条对话 | 最新（`updated_at DESC`）/ 最早（`created_at ASC`） | 最新 |
| **D2** | 迁移脚本放在哪个目录 | `migrations/` / `scripts/migrations/` | `migrations/` |
| **D3** | `schema_migrations` 表是否持久化 | 是 / 否（测试环境可删） | 是 |
| **D4** | Chat.vue 选择历史会话时是否保留 `activeTripId` | 保留 / 清空（现有行为） | 清空（历史会话与行程解绑） |
