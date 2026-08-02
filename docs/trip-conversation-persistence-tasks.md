# Trip 对话持久化 — 实施任务清单

> **文档状态**：草案 v1.0  
> **日期**：2026-08-01  
> **对应 TDD**：`docs/trip-conversation-persistence-tdd.md`  
> **实施范围**：方案 A（`conversations` 表新增 `trip_id` 字段）

---

## 任务依赖图

```
T1 ──→ T2 ──→ T3 ──→ T4
         │         │
         │         ├─→ T6 ──→ T7
         │
         ├─→ T5 ──→ T8 ──→ T9
```

| 阶段 | 任务 | 依赖 |
|---|---|---|
| **Phase 1: 数据层** | T1: 数据库迁移 | 无 |
| | T2: 后端模型改动 | T1 |
| | T3: 迁移执行 + 验证 | T2 |
| | T4: ORM 反向关系补充 | T2 |
| **Phase 2: 后端接口层** | T5: Service 层新增 `get_by_trip_id` | T2 |
| | T6: `_get_or_create_conversation` 透传 `trip_id` | T4 |
| | T7: Controller 新增 `by-trip` 端点 | T5, T6 |
| **Phase 3: 前端接入层** | T8: 前端 API 新增 `getConversationByTripId` | T7 |
| | T9: Chat.vue 按 tripId 查找已有对话 | T8 |
| **Phase 4: 验证** | T10: 后端测试 | T3, T7 |
| | T11: 前端验证 | T9 |
| | T12: PRD 验收回归 | T10, T11 |

---

## Phase 1: 数据层

### T1: 数据库迁移脚本

**文件**：`migrations/001_add_trip_id_to_conversations.sql`（新建）

**前置条件**：无

#### 清单

- [ ] T1.1 创建 `migrations/` 目录（若不存在）
- [ ] T1.2 编写 `001_add_trip_id_to_conversations.sql`：
  - `ALTER TABLE conversations ADD COLUMN trip_id INTEGER;`
  - `ALTER TABLE conversations ADD CONSTRAINT fk_conversations_trip_id FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE SET NULL;`
  - `CREATE INDEX idx_conversations_trip_id ON conversations(trip_id);`
  - 验证查询 `SELECT column_name, is_nullable FROM information_schema.columns ...`
- [ ] T1.3 确认 SQL 语法与 PostgreSQL 兼容（项目使用 PostgreSQL + asyncpg）

#### 流程

```
开发环境执行：
  psql -U trip -d trip_db -f migrations/001_add_trip_id_to_conversations.sql
  
生产环境执行（低峰期）：
  1. 先执行 ALTER TABLE ADD COLUMN（毫秒级）
  2. 再执行 CREATE INDEX（可 CONCURRENTLY，不锁表）
  3. 执行验证查询确认列存在
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T1-AC1** | 执行迁移脚本 | `conversations` 表新增 `trip_id` 列，类型 `INTEGER`，可空 |
| **T1-AC2** | 执行迁移脚本 | 外键 `fk_conversations_trip_id` 存在，引用 `trips.id`，`ON DELETE SET NULL` |
| **T1-AC3** | 执行迁移脚本 | 索引 `idx_conversations_trip_id` 存在 |
| **T1-AC4** | 执行验证查询 | 返回 `trip_id` 行，`is_nullable = YES` |
| **T1-AC5** | 重复执行迁移脚本 | 幂等：列已存在时 `ALTER TABLE` 报错但不影响后续（需手动处理或加 `IF NOT EXISTS`） |

**注意**：PostgreSQL 的 `ALTER TABLE ... ADD COLUMN` 在列已存在时会报错。建议迁移脚本开头增加：
```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'conversations' AND column_name = 'trip_id'
    ) THEN
        ALTER TABLE conversations ADD COLUMN trip_id INTEGER;
    END IF;
END $$;
```

---

### T2: 后端模型改动

**文件**：
- `src/models/conversation.py`（修改）
- `src/models/trip.py`（修改）

**依赖**：T1

#### 清单

- [ ] T2.1 修改 `src/models/conversation.py`：
  - 新增 `trip_id` 字段（`Column(Integer, ForeignKey("trips.id"), nullable=True, index=True)`）
  - 新增 `trip` relationship（`relationship("Trip", back_populates="conversations")`）
- [ ] T2.2 修改 `src/models/trip.py`：
  - 新增 `conversations` relationship（`relationship("Conversation", back_populates="trip", cascade="all, delete-orphan")`）
- [ ] T2.3 确认 `Base.metadata` 已包含新字段（启动时 `create_all` 不会重复报错）

#### 流程

```python
# src/models/conversation.py — 修改后

class Conversation(Base, BaseModel):
    __tablename__ = "conversations"
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
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    token_logs = relationship(
        "TokenUsageLog",
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
```

```python
# src/models/trip.py — 修改后

class Trip(Base, BaseModelWithoutUpdatedAt):
    __tablename__ = "trips"
    # ... 现有字段 ...
    
    # Relationships
    user = relationship("User", back_populates="trips")
    parent = relationship(
        "Trip",
        remote_side="Trip.id",
        back_populates="versions",
        foreign_keys=[parent_trip_id]
    )
    versions = relationship(
        "Trip",
        back_populates="parent",
        foreign_keys=[parent_trip_id]
    )
    conversations = relationship(  # 新增
        "Conversation",
        back_populates="trip",
        cascade="all, delete-orphan"
    )
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T2-AC1** | 启动 FastAPI（`init_db`） | 无报错，`Base.metadata` 包含新字段 |
| **T2-AC2** | SQLAlchemy 反射 `Conversation.__table__` | 包含 `trip_id` 列 |
| **T2-AC3** | SQLAlchemy 反射 `Trip.__table__` | 未变（`trip_id` 在 `conversations` 表） |
| **T2-AC4** | 查询 `Conversation.trip` relationship | 可正常访问（需已有数据） |

---

### T3: 迁移执行 + 验证

**文件**：`migrations/001_add_trip_id_to_conversations.sql`

**依赖**：T1, T2

#### 清单

- [ ] T3.1 在开发环境执行迁移脚本
- [ ] T3.2 验证 `conversations` 表结构：
  - `\d conversations` 查看列定义
  - 确认 `trip_id` 存在且可空
  - 确认外键存在
  - 确认索引存在
- [ ] T3.3 验证存量数据：
  - `SELECT COUNT(*) FROM conversations WHERE trip_id IS NULL;` — 应为总行数（存量无关联）
  - `SELECT COUNT(*) FROM conversations WHERE trip_id IS NOT NULL;` — 应为 0（新建对话才写入）
- [ ] T3.4 验证外键约束：
  - 插入 `trip_id = 99999`（不存在的行程）→ 应报外键错误
- [ ] T3.5 验证索引有效性：
  - `EXPLAIN ANALYZE SELECT * FROM conversations WHERE trip_id = 123;` — 应使用索引

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T3-AC1** | 查看表结构 | `trip_id` 列存在，类型 `integer`，可空 |
| **T3-AC2** | 查看外键 | `fk_conversations_trip_id` 存在，引用 `trips(id)`，`ON DELETE SET NULL` |
| **T3-AC3** | 查看索引 | `idx_conversations_trip_id` 存在 |
| **T3-AC4** | 插入无效 `trip_id` | 外键约束报错（验证外键生效） |
| **T3-AC5** | 查询计划 | 使用 `idx_conversations_trip_id` 索引 |

---

### T4: ORM 反向关系补充

**文件**：`src/models/trip.py`

**依赖**：T2

#### 清单

- [ ] T4.1 确认 `Trip.conversations` relationship 已添加（T2.2 已完成）
- [ ] T4.2 编写简单测试验证反向关系：
  ```python
  trip = await HistoryService.get_trip(db, trip_id, user_id)
  conv = Conversation(user_id=user_id, title="test", trip_id=trip.id)
  db.add(conv)
  await db.commit()
  assert trip.conversations[0].id == conv.id
  ```
- [ ] T4.3 验证级联删除行为：
  ```python
  await HistoryService.delete_trip(db, trip_id, user_id)
  conv_after = await ConversationService.get_conversation(db, conv.id, user_id)
  assert conv_after.trip_id is None  # ON DELETE SET NULL
  ```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T4-AC1** | `trip.conversations` 反向查询 | 返回关联的 conversation 列表 |
| **T4-AC2** | 删除行程 | 关联 conversation 的 `trip_id` 变为 NULL，对话本身不删除 |

---

## Phase 2: 后端接口层

### T5: Service 层新增 `get_by_trip_id`

**文件**：`src/services/conversation_service.py`

**依赖**：T2

#### 清单

- [ ] T5.1 新增 `ConversationService.get_by_trip_id(db, trip_id, user_id)`：
  - 调用 `HistoryService.get_trip(db, trip_id, user_id)` 验证行程存在
  - 查询 `Conversation` 表：`trip_id = ? AND user_id = ?`，按 `updated_at DESC`，`LIMIT 1`
  - 预加载 `messages`（`selectinload(Conversation.messages)`）
  - 未找到时抛出 `NotFoundException("行程关联对话")`
- [ ] T5.2 编写单元测试：
  - 创建行程 + 用户
  - 创建关联对话（`trip_id = 行程ID`）
  - 调用 `get_by_trip_id` → 返回对话
  - 调用 `get_by_trip_id`（无关联对话）→ `NotFoundException`
  - 调用 `get_by_trip_id`（他人行程）→ `NotFoundException`

#### 流程

```
调用方: GET /api/conversations/by-trip/123
  │
  ▼
ConversationService.get_by_trip_id(db, 123, user_id=1)
  │
  ├─ HistoryService.get_trip(db, 123, 1) → 验证行程存在且属于该用户
  │   └─ 行程不存在 → NotFoundException("行程")
  │
  ├─ SELECT * FROM conversations 
  │   WHERE trip_id = 123 AND user_id = 1 
  │   ORDER BY updated_at DESC LIMIT 1
  │   （带 selectinload(messages)）
  │
  ├─ 找到 → return conversation
  └─ 未找到 → NotFoundException("行程关联对话")
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T5-AC1** | 行程存在且有关联对话 | 返回对话对象（含 messages） |
| **T5-AC2** | 行程存在但无关联对话 | `NotFoundException` |
| **T5-AC3** | 行程不存在 | `NotFoundException`（行程级） |
| **T5-AC4** | 他人行程 | `NotFoundException`（权限控制） |
| **T5-AC5** | 同一行程多个对话 | 返回 `updated_at` 最新的一个 |

---

### T6: `_get_or_create_conversation` 透传 `trip_id`

**文件**：`src/services/trip_service.py`

**依赖**：T4

#### 清单

- [ ] T6.1 修改 `_get_or_create_conversation` 签名：
  - 新增参数 `trip_id: Optional[int] = None`
- [ ] T6.2 修改复用已有对话的逻辑：
  - 若 `conv.trip_id is None and trip_id is not None` → 回写 `conv.trip_id = trip_id`，`commit + refresh`
- [ ] T6.3 修改新建对话的逻辑：
  - `Conversation(user_id=user_id, title="新对话", trip_id=trip_id)`
- [ ] T6.4 修改 `chat_stream` 调用：
  - `_get_or_create_conversation(user_id, conversation_id, trip_id=trip_id)`
- [ ] T6.5 编写/更新测试：
  - `test_chat_stream_creates_conversation` → 验证新建对话时 `trip_id` 写入
  - `test_chat_stream_uses_existing_conversation` → 验证复用对话时 `trip_id` 回写

#### 流程

```python
# 路径 A：复用已有对话
_get_or_create_conversation(user_id=1, conversation_id=456, trip_id=123)
  │
  ├─ 查库：Conversation.id = 456 AND user_id = 1
  ├─ 找到 conv（trip_id 原为 NULL）
  ├─ 回写：conv.trip_id = 123
  ├─ commit + refresh
  └─ return conv

# 路径 B：创建新对话
_get_or_create_conversation(user_id=1, conversation_id=None, trip_id=123)
  │
  ├─ conversation_id 为 None → 跳过查找
  ├─ 创建：Conversation(user_id=1, title="新对话", trip_id=123)
  ├─ commit + refresh
  └─ return conv
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T6-AC1** | 新建对话（conversation_id=None, trip_id=123） | 新对话 `trip_id = 123` |
| **T6-AC2** | 复用对话（conversation_id=456, 原 trip_id=NULL, trip_id=123） | 回写后 `trip_id = 123` |
| **T6-AC3** | 复用对话（conversation_id=456, 原 trip_id=123, trip_id=123） | 不变，`trip_id` 仍为 123 |
| **T6-AC4** | 新建对话（conversation_id=None, trip_id=None） | 新对话 `trip_id = NULL`（存量行为） |

---

### T7: Controller 新增 `by-trip` 端点

**文件**：
- `src/controllers/conversation_controller.py`（新增路由）
- `src/schemas/conversation.py`（可选：新增 `ConversationResponse` 的 `tripId` 字段）

**依赖**：T5, T6

#### 清单

- [ ] T7.1 新增路由 `GET /api/conversations/by-trip/{trip_id}`：
  - 调用 `ConversationService.get_by_trip_id(db, trip_id, current_user.id)`
  - 序列化为 `ConversationResponse`（含 `tripId`）
  - 异常处理：`NotFoundException` → 404
- [ ] T7.2 修改 `ConversationResponse` Schema：
  - 新增 `trip_id: Optional[int] = Field(default=None, alias="tripId")`
- [ ] T7.3 修改 `conversation_controller.py` 中已有的 `get_conversation` 和 `get_conversations`：
  - 在返回的 dict 中包含 `trip_id` 字段
- [ ] T7.4 编写接口测试：
  - `GET /api/conversations/by-trip/123`（有对话）→ 200 + 对话详情
  - `GET /api/conversations/by-trip/123`（无对话）→ 404
  - `GET /api/conversations/by-trip/999`（他人行程）→ 404
  - `GET /api/conversations/by-trip/123`（未登录）→ 401

#### 流程

```
前端请求: GET /api/conversations/by-trip/123
Authorization: Bearer <token>
  │
  ▼
FastAPI Router: /conversations/by-trip/{trip_id}
  │
  ▼
get_conversation_by_trip(trip_id=123, current_user, db)
  │
  ├─ ConversationService.get_by_trip_id(db, 123, current_user.id)
  │   ├─ HistoryService.get_trip(db, 123, current_user.id) → 验证行程
  │   └─ SELECT ... WHERE trip_id=123 AND user_id=current_user.id ORDER BY updated_at DESC LIMIT 1
  │
  ├─ 找到 → 序列化为 ConversationResponse（含 tripId）
  │   return { code: 200, data: conversation_dict, ... }
  └─ 未找到 → raise NotFoundException → 404
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T7-AC1** | `GET /api/conversations/by-trip/123`（有对话） | 200 + `{ id, tripId, title, messages }` |
| **T7-AC2** | `GET /api/conversations/by-trip/123`（无对话） | 404 + `{ code: 404, message: "行程无关联对话" }` |
| **T7-AC3** | `GET /api/conversations/by-trip/999`（行程不存在） | 404 |
| **T7-AC4** | `GET /api/conversations/by-trip/123`（未登录） | 401 |
| **T7-AC5** | `ConversationResponse` 包含 `tripId` | 序列化后 camelCase 为 `tripId` |

---

## Phase 3: 前端接入层

### T8: 前端 API 新增 `getConversationByTripId`

**文件**：
- `trip-front/src/api/conversation.ts`（新增接口）
- `trip-front/src/api/request.ts`（若需要，确认已有 `get` 方法）

**依赖**：T7

#### 清单

- [ ] T8.1 修改 `trip-front/src/api/conversation.ts`：
  - 新增 `ConversationByTripResponse` 接口
  - 新增 `getConversationByTripId(tripId: number)` 函数
- [ ] T8.2 确认 `request.ts` 的 `get` 方法支持带路径参数（应已支持）
- [ ] T8.3 前端类型检查：`vue-tsc` 无错误

#### 代码

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

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T8-AC1** | 调用 `getConversationByTripId(123)`（有对话） | 返回 `{ id, tripId, messages }` |
| **T8-AC2** | 调用 `getConversationByTripId(123)`（无对话） | 抛出 404 错误 |
| **T8-AC3** | `vue-tsc` 类型检查 | 零错误 |

---

### T9: Chat.vue 按 tripId 查找已有对话

**文件**：`trip-front/src/views/Chat.vue`

**依赖**：T8

#### 清单

- [ ] T9.1 导入 `getConversationByTripId`
- [ ] T9.2 修改 `onMounted` 逻辑：
  - 保留现有 `localStorage` 读取逻辑
  - 新增：若 `route.query.tripId` 有效且 `currentConversationId` 为 null → 调用 `getConversationByTripId`
  - 成功时：设置 `currentConversationId`，写入 `localStorage`，加载历史消息
  - 失败时：404 降级为空对话，其他错误调用 `handleApiError`
- [ ] T9.3 边界处理：
  - `tripId` 为 0 / 负数 / 非数字 → 跳过查找
  - `currentConversationId` 已有值（localStorage 有记录）→ 跳过查找
  - 网络错误 → 降级为空对话
- [ ] T9.4 前端测试（可选，若项目有前端测试）：
  - mock `getConversationByTripId` 返回对话 → 验证消息加载
  - mock `getConversationByTripId` 返回 404 → 验证空对话
- [ ] T9.5 手动验证：
  - 打开 `/chat?tripId=123`（有对话）→ 显示历史消息
  - 打开 `/chat?tripId=123`（无对话）→ 空对话
  - 打开 `/chat`（无 tripId）→ 原有行为不变

#### 流程

```typescript
onMounted(async () => {
  // 1. 现有逻辑：读取 localStorage
  const stored = typeof window !== 'undefined' ? localStorage.getItem(CONVERSATION_ID_KEY) : null
  const parsedStored = stored ? Number(stored) : NaN
  currentConversationId.value = Number.isInteger(parsedStored) ? parsedStored : null
  if (currentConversationId.value == null && typeof window !== 'undefined') {
    localStorage.removeItem(CONVERSATION_ID_KEY)
  }

  // 2. 新增：按 tripId 查找已有对话
  const tripIdFromQuery = Number(route.query.tripId)
  if (
    Number.isInteger(tripIdFromQuery) &&
    tripIdFromQuery > 0 &&
    !currentConversationId.value  // localStorage 无记录时才查找
  ) {
    try {
      const res = await getConversationByTripId(tripIdFromQuery)
      const conv = res.data
      if (conv?.id) {
        currentConversationId.value = conv.id
        localStorage.setItem(CONVERSATION_ID_KEY, String(conv.id))
        messages.value = (conv.messages || []).map(m => ({
          id: m.id,
          role: m.role === 'user' ? 'user' : 'ai',
          content: m.content,
          timestamp: m.createdAt,
        }))
      }
    } catch (e) {
      // 404 静默降级（行程无对话）
      if ((e as any)?.response?.status !== 404) {
        handleApiError(e, message)
      }
    }
  }

  loadConversations()
})
```

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T9-AC1** | `/chat?tripId=123`（有对话） | 加载历史消息，`currentConversationId` = 对话 ID |
| **T9-AC2** | `/chat?tripId=123`（无对话） | 空对话，`currentConversationId` = null |
| **T9-AC3** | `/chat`（无 tripId） | 原有行为不变 |
| **T9-AC4** | `/chat?tripId=abc`（非数字） | 跳过查找，原有行为 |
| **T9-AC5** | `/chat?tripId=0` | 跳过查找，原有行为 |
| **T9-AC6** | 接口 500 错误 | `handleApiError` 提示，不阻断页面加载 |

---

## Phase 4: 验证

### T10: 后端测试

**文件**：
- `trip-backend/tests/test_conversation_trip_persistence.py`（新建）

**依赖**：T3, T7

#### 清单

- [ ] T10.1 新建 `tests/test_conversation_trip_persistence.py`
- [ ] T10.2 编写测试用例：
  - `test_get_by_trip_id_returns_latest` — 返回最新对话
  - `test_get_by_trip_id_404_when_no_conversation` — 无对话返回 404
  - `test_get_by_trip_id_404_when_trip_not_found` — 行程不存在返回 404
  - `test_get_by_trip_id_forbidden_for_other_user` — 他人行程返回 404
  - `test_create_conversation_with_trip_id` — 新建对话写入 `trip_id`
  - `test_reuse_conversation_backfills_trip_id` — 复用对话回写 `trip_id`
  - `test_delete_trip_sets_trip_id_null` — 删除行程后 `trip_id` 为 NULL
- [ ] T10.3 运行测试：`.venv/bin/python -m pytest tests/test_conversation_trip_persistence.py -v`

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T10-AC1** | 全部测试通过 | `7 passed` |
| **T10-AC2** | 新增测试覆盖 `get_by_trip_id` | 4 个场景（正常/无对话/行程不存在/权限） |
| **T10-AC3** | 新增测试覆盖 `_get_or_create_conversation` trip_id 透传 | 3 个场景（新建/复用回写/复用已有） |
| **T10-AC4** | 新增测试覆盖删除行程级联 | 1 个场景 |

---

### T11: 前端验证

**文件**：手动验证（`trip-front` 开发服务器）

**依赖**：T9

#### 清单

- [ ] T11.1 启动前端开发服务器：`npm run dev`
- [ ] T11.2 启动后端服务（连接测试数据库）
- [ ] T11.3 手动验证场景（需提前准备测试数据）：
  - 用户 A 创建行程 123，在 ChatPanel 对话 → 生成 conversation 456
  - 打开 `/chat?tripId=123` → 应加载 conversation 456
  - 在 `/chat?tripId=123` 发送消息 → conversationId 仍为 456
  - 切回 `/detail?id=123` → ChatPanel 加载 conversation 456
  - 刷新 `/detail?id=123` → ChatPanel 恢复 conversation 456
- [ ] T11.4 边界验证：
  - `/chat?tripId=999`（无行程）→ 空对话
  - `/chat`（无 tripId）→ 原有行为
  - 清除 localStorage → 重新打开 `/chat?tripId=123` → 后端仍能找到对话

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T11-AC1** | ChatPanel ↔ Chat.vue 同一行程 | 同一 conversationId，消息互通 |
| **T11-AC2** | 刷新页面 | 对话不丢失 |
| **T11-AC3** | 清除 localStorage | 后端仍能找到对话 |
| **T11-AC4** | `/chat` 无 tripId | 原有行为不变 |

---

### T12: PRD 验收回归

**对应 PRD**：`docs/trip-conversation-persistence-prd.md` §4

**依赖**：T10, T11

#### 清单

- [ ] T12.1 逐条验证 PRD 功能验收（AC1-AC8）：
  - AC1: ChatPanel 发送消息 → 持久化
  - AC2: Detail → Chat 同一对话
  - AC3: Chat 发送消息 → 同一对话
  - AC4: Chat → Detail 同一对话
  - AC5: 刷新 Detail → 对话保持
  - AC6: 关闭重开 Detail → 对话保持
  - AC7: 切换行程版本 → 对话迁移
  - AC8: 清除 localStorage → 后端兜底
- [ ] T12.2 逐条验证 PRD 异常验收（AC9-AC12）：
  - AC9: `/chat` 无 tripId → 通用对话
  - AC10: `/chat?tripId=999` → 正常提示
  - AC11: `/chat?tripId=123` 无对话 → 创建新对话
  - AC12: 后端 500 → 前端降级
- [ ] T12.3 数据验收 checklist：
  - [ ] `conversations` 表有 `trip_id` 字段
  - [ ] 新对话写入 `trip_id`
  - [ ] `GET /api/trips/{tripId}/conversation` 可用
  - [ ] ChatPanel 保留 `trip_panel_conv_${tripId}`
  - [ ] Chat.vue 按 tripId 查找

#### 验收标准

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **T12-AC1** | AC1-AC8 全部通过 | 8/8 ✅ |
| **T12-AC2** | AC9-AC12 全部通过 | 4/4 ✅ |
| **T12-AC3** | 数据验收 checklist | 5/5 ✅ |

---

## 附录 A: 快速启动命令

```bash
# 后端
cd trip-backend
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000

# 前端
cd trip-front
npm run dev

# 后端测试
cd trip-backend
.venv/bin/python -m pytest tests/test_conversation_trip_persistence.py -v

# 数据库迁移（开发环境）
cd trip-backend
psql -U trip -d trip_db -f migrations/001_add_trip_id_to_conversations.sql
```

---

## 附录 B: 回滚方案

若实施过程中出现问题，可按以下步骤回滚：

| 步骤 | 操作 |
|---|---|
| 1 | 回滚代码：`git revert <commit_range>` |
| 2 | 回滚数据库：`ALTER TABLE conversations DROP COLUMN trip_id;` |
| 3 | 删除索引：`DROP INDEX IF EXISTS idx_conversations_trip_id;` |
| 4 | 删除外键：`ALTER TABLE conversations DROP CONSTRAINT IF EXISTS fk_conversations_trip_id;` |
| 5 | 重启服务 |

**注意**：回滚数据库会丢失已关联的 `trip_id` 数据（可接受，因为关联关系本身是新增功能）。

---

## 附录 C: Git 提交建议

```bash
# Phase 1: 数据层
git commit -m "feat(conversation): add trip_id field + migration

- Add migrations/001_add_trip_id_to_conversations.sql
- Update Conversation model with trip_id FK
- Update Trip model with conversations relationship
- Add src/utils/migrations.py for pending migration execution"

# Phase 2: 后端接口层
git commit -m "feat(conversation): add get_by_trip_id endpoint

- ConversationService.get_by_trip_id() with auth check
- _get_or_create_conversation backfill trip_id
- New GET /api/conversations/by-trip/{tripId} endpoint
- ConversationResponse includes tripId"

# Phase 3: 前端接入层
git commit -m "feat(chat): Chat.vue loads conversation by tripId

- Add getConversationByTripId() API
- Chat.vue onMounted lookup existing conversation by tripId
- ChatPanel.vue unchanged (already has trip-scoped persistence)"

# Phase 4: 验证
git commit -m "test(conversation): add trip persistence tests

- test_conversation_trip_persistence.py (7 tests)
- Cover get_by_trip_id, backfill, cascade delete"
```
