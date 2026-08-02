# Trip 对话持久化 PRD — 一行程一对话

> **文档状态**：草案 v1.0  
> **日期**：2026-08-01  
> **提出人**：产品主理人  
> **下游消费者**：前端（trip-front）、后端（trip-backend）  
> **上游输入**：代码库现状分析（Detail.vue / Chat.vue / ChatPanel.vue / conversation_controller.py）

---

## 1. 背景与痛点

### 1.1 现状

当前产品存在两个独立的对话入口：

| 入口 | 组件 | 路由 | localStorage Key | 隔离方式 |
|---|---|---|---|---|
| **行程内嵌对话** | `ChatPanel.vue` | `/detail?id=<tripId>` | `trip_panel_conv_${tripId}` | 按 tripId 隔离 |
| **独立对话页** | `Chat.vue` | `/chat` | `trip_chat_conversation_id` | 全局单 key |

后端 `Conversation` 模型（`conversations` 表）**没有 `trip_id` 字段**，对话与行程在数据库层面没有任何关联。

### 1.2 用户可感知的问题

**核心痛点：同一个行程，在不同入口对话会产生多个独立对话，上下文完全断裂。**

具体表现：
1. 用户在 `/detail?id=123` 的内嵌 ChatPanel 里聊了 10 轮，修改了行程
2. 用户切到侧边栏 `/chat` 独立页——看不到之前的对话历史，因为 Chat.vue 用的是另一套 localStorage key
3. 用户在 `/chat` 里又聊了 5 轮
4. 用户切回 `/detail?id=123`——仍然看不到 `/chat` 里的 5 轮对话
5. **结果**：行程 123 对应了两个（甚至更多）互不相通的对话，用户需要重复交代上下文

**次要痛点：localStorage 一旦被清空，对话即丢失。**

- 用户清除浏览器缓存、或使用隐私模式、或 localStorage 过期
- 再次打开行程时，`restoreConversation()` 读不到 conversationId
- 后端 `_get_or_create_conversation` 发现 `conversation_id` 为 null → **静默创建新对话**
- 用户完全感知不到"对话已重置"，直到发现上下文消失了

### 1.3 根本原因

| 层级 | 问题 |
|---|---|
| **数据模型** | `Conversation` 表无 `trip_id`，无法按行程查找/关联对话 |
| **前端存储** | ChatPanel 与 Chat.vue 使用两套完全独立的 localStorage key，互不通信 |
| **路由协议** | `/chat` 页面不感知当前活跃行程，URL 不带 `tripId` 时无法关联 |
| **容错策略** | `restoreConversation` 失败时直接清空 localStorage，不做降级查找 |

---

## 2. 目标与非目标

### 2.1 目标（Goals）

| 编号 | 目标 | 度量方式 |
|---|---|---|
| **G1** | **一个行程只有一个对话** | 同一 tripId 在任何入口（Detail 内嵌 / Chat 独立页）打开，始终指向同一个 conversationId |
| **G2** | **对话在页面刷新/重开后保持连续** | 关闭标签页再打开、刷新页面、切换行程版本，对话不丢失 |
| **G3** | **对话与行程强关联** | 数据库中 `conversation` 可通过 `trip_id` 反查，支持"查看行程的所有对话" |

### 2.2 非目标（Non-goals）

| 编号 | 非目标 | 原因 |
|---|---|---|
| **NG1** | 不支持一个行程对应多个对话 | 现阶段产品定位就是"一行程一对话"，多对话场景后续可按需扩展 |
| **NG2** | 不迁移现有历史对话数据 | 存量 `conversations` 表数据保持不动，新关联逻辑仅对新对话生效 |
| **NG3** | 不修改前端整体路由架构 | 保留 `/detail` 和 `/chat` 两个路由，不合并为一个页面 |
| **NG4** | 不涉及 SSE 流式传输改造 | 保持现有 `X-Stream-Id` + `Last-Event-ID` 断点续传机制不变 |

---

## 3. 关键流程

### 3.1 目标状态：一行程一对话的完整生命周期

```
用户打开 /detail?id=123
        │
        ▼
  Detail.vue 加载 currentTripMeta = { id: 123 }
        │
        ▼
  ChatPanel 挂载
        │
        ├─ 读取 localStorage: trip_panel_conv_123
        │   └─ 有值 → 恢复该 conversation，加载历史消息 ✅
        │   └─ 无值 → 发起新对话请求（后端创建或复用）
        │
        ▼
  用户在 ChatPanel 中对话
        │
        ▼
  SSE complete → conversationId = 456
        │
        ▼
  持久化: localStorage.setItem('trip_panel_conv_123', '456')
        │
        ▼
  用户导航到 /chat?tripId=123
        │
        ▼
  Chat.vue 挂载
        │
        ├─ 读取 URL query: tripId = 123
        ├─ 读取 localStorage: trip_chat_conversation_id（可选 fallback）
        │
        ├─ 调用 GET /api/trips/123/conversation（新接口）
        │   └─ 返回 { conversationId: 456 } → 复用已有对话 ✅
        │   └─ 返回 404（行程无对话） → 走正常新建流程
        │
        ▼
  用户在 Chat.vue 中继续同一对话（conversationId = 456）
        │
        ▼
  SSE complete → conversationId 仍为 456
        │
        ▼
  用户切回 /detail?id=123
        │
        ▼
  ChatPanel 重新挂载 → 读取 trip_panel_conv_123 → 456 → 同一对话 ✅
```

### 3.2 关键决策点

**决策 1：对话查找的权威来源**

| 方案 | 说明 | 推荐 |
|---|---|---|
| **A. 前端 localStorage 为主，后端 API 为 fallback** | ChatPanel 优先读 `trip_panel_conv_${tripId}`；Chat.vue 优先调用后端接口查找 | ✅ 推荐 |
| **B. 后端 API 为主，localStorage 为辅** | 所有入口先调后端 `GET /api/trips/{tripId}/conversation` | 次选，增加 API 调用 |

**决策 2：Conversation 与 Trip 的关联方式**

| 方案 | 说明 | 推荐 |
|---|---|---|
| **A. conversations 表新增 `trip_id` 字段** | 直接在对话表加外键，简单直接 | ✅ 推荐 |
| **B. 新增 trips_conversations 关联表** | 支持一对多（未来可能一个行程多个对话） | 次选，当前非目标 |

**决策 3：独立页 `/chat` 的默认行为**

| 方案 | 说明 | 推荐 |
|---|---|---|
| **A. URL 必须带 `?tripId=xxx` 才关联行程** | `/chat` 不带 tripId 时显示"未关联行程"或通用对话 | ✅ 推荐 |
| **B. 自动关联最近操作的行程** | 从 localStorage 读最近 tripId | 次选，逻辑隐晦 |

---

## 4. 验收标准

### 4.1 功能验收（P0）

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **AC1** | 用户在 `/detail?id=123` 内嵌 ChatPanel 发送消息 | 创建/复用 conversationId，存入 `trip_panel_conv_123` |
| **AC2** | 用户从 `/detail?id=123` 点击侧边栏进入 `/chat?tripId=123` | Chat.vue 调用后端接口，找到同一 conversationId，加载相同历史消息 |
| **AC3** | 用户在 `/chat?tripId=123` 发送消息 | conversationId 不变，消息追加到同一对话 |
| **AC4** | 用户从 `/chat?tripId=123` 返回 `/detail?id=123` | ChatPanel 恢复同一 conversationId，历史消息一致 |
| **AC5** | 用户刷新 `/detail?id=123` | ChatPanel 从 localStorage 恢复同一 conversation，不创建新对话 |
| **AC6** | 用户关闭标签页重新打开 `/detail?id=123` | 对话持久化有效，恢复同一 conversation |
| **AC7** | 用户在 `/detail` 切换行程版本（id 从 123 变为 456） | ChatPanel 将 conversationId 迁移到 `trip_panel_conv_456`，123 的历史独立保留 |
| **AC8** | 用户清除 localStorage 后重新打开行程 | 后端仍可通过 `trip_id` 查找到对话（如果已持久化），不盲目创建新对话 |

### 4.2 异常验收（P1）

| 编号 | 场景 | 预期结果 |
|---|---|---|
| **AC9** | 访问 `/chat` 不带 `tripId` | 显示通用对话界面，不影响已有行程对话 |
| **AC10** | 访问 `/chat?tripId=999`（行程不存在） | 正常提示，不崩溃 |
| **AC11** | 访问 `/chat?tripId=123`（行程存在但无对话） | 创建新对话并关联，后续可找回 |
| **AC12** | 后端 `/api/trips/{tripId}/conversation` 返回 500 | 前端降级为显示空对话，不阻断用户使用 |

### 4.3 数据验收

- [ ] `conversations` 表新增 `trip_id` 字段（可空，nullable）
- [ ] 新创建/复用的对话写入 `trip_id`
- [ ] 后端提供 `GET /api/trips/{tripId}/conversation` 接口，返回关联的 conversation（含消息）
- [ ] 前端 `ChatPanel.vue` 保留 `trip_panel_conv_${tripId}` 策略
- [ ] 前端 `Chat.vue` 增加按 `tripId` 查找已有对话的逻辑

---

## 5. 风险清单

| 编号 | 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|---|
| **R1** | **存量对话无法追溯 trip_id** | 高 | 中 | 新增 `trip_id` 字段设为 nullable；存量数据为 null 不影响现有功能；新对话才写入关联 |
| **R2** | **前端 localStorage 与后端数据库不一致** | 中 | 高 | 以数据库为权威来源；localStorage 仅作缓存；`GET /api/trips/{tripId}/conversation` 优先查库 |
| **R3** | **用户刻意想在同一行程开多个对话** | 低 | 低 | 当前产品定位为"一行程一对话"；如后续需要，可通过"新建对话"按钮覆盖，不阻断 |
| **R4** | **`/chat` 不带 tripId 时的行为歧义** | 中 | 低 | 明确设计：不带 tripId 显示通用对话；入口处提示"关联行程后可查看行程上下文" |
| **R5** | **切换行程版本时 conversationId 迁移出错** | 中 | 中 | ChatPanel 已有迁移逻辑（`watch props.tripId`），需增加迁移成功后的后端同步（更新 `trip_id`） |
| **R6** | **删除行程后关联对话成为"孤儿"** | 低 | 低 | 当前无行程删除 API；如后续添加，级联处理或软删除 |
| **R7** | **多端同步问题**（用户手机和电脑同时用） | 中 | 中 | localStorage 是单设备单浏览器；跨设备需登录态 + 服务端拉取。本轮 scope 内可暂缓，后续通过"对话列表"接口解决 |

---

## 6. 后续设计稿待输出

完成本 PRD 评审后，需补充以下文档：

| 文档 | 内容 |
|---|---|
| **技术设计文档（TDD）** | 数据库迁移脚本、后端接口定义、前端状态管理改动 |
| **接口契约** | `GET /api/trips/{tripId}/conversation` 的请求/响应 schema |
| **数据迁移方案** | `conversations` 表加 `trip_id` 字段的 migration 策略 |
| **前端路由改造方案** | Chat.vue 如何感知 tripId、如何与 ChatPanel 共享状态 |
