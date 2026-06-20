# Agent 上下文管理改进方案

> 对现有对话记忆系统的四项升级：增量摘要、自适应 Token 窗口、压缩重试、分层摘要。

---

## 一、改前 vs 改后

```
改进前：
┌──────────────────────────────────────────────────┐
│ 固定 20 条消息 → 超出 → 全量替换摘要 →             │
│ 失败静默丢弃 → 只有关键决策、无对话脉络              │
└──────────────────────────────────────────────────┘

改进后：
┌──────────────────────────────────────────────────┐
│ Token 自适应窗口 (8000 tokens) → 超出 →             │
│ 增量追加摘要（合并新旧） → 分层输出（决策+脉络）      │
│ → 最多 2 次重试 → 失败标记 summaryError             │
└──────────────────────────────────────────────────┘
```

---

## 二、新增文件

| 文件 | 说明 |
|---|---|
| `trip-server/src/utils/tokens.ts` | Token 估算工具 + 环境变量读取 |

## 三、修改文件

| 文件 | 改动 |
|---|---|
| `trip-server/src/services/summaryService.ts` | 增量追加 + 分层输出 + 重试 + 失败标记 |
| `trip-server/src/services/conversationService.ts` | Token 窗口 + recap 加载 |
| `trip-server/src/services/agent/systemPrompt.ts` | conversationRecap 上下文注入 |
| `trip-server/src/services/agent/agentEngine.ts` | 传递 conversationRecap |
| `trip-server/prisma/schema.prisma` | Conversation 新增 recap、summaryError、summaryAt |

## 四、环境变量

```bash
HISTORY_MAX_TOKENS=8000  # 对话历史 token 上限，默认 8000（约 50-60 条中文消息）
```

---

## 五、各项详解

### 5.1 增量摘要（追加模式）

**问题**：每次压缩全量覆盖 `conversation.summary`，旧摘要丢掉。

**方案**：压缩时读取已有摘要 → 与新消息合并后交给 LLM → 输出完整摘要。

**LLM Prompt 差异**：

| 首次压缩 | 已有摘要时 |
|---|---|
| "请概括以下对话..." | "已有摘要 + 新对话 → 合并输出" |

**效果**：摘要 "用户想去成都..." → 后续聊了北京 → 摘要更新为 "用户想去成都...后续询问北京长城..."

---

### 5.2 自适应 Token 窗口

**问题**：固定 20 条消息——Agent 返回长篇行程时可能超 LLM 上下文上限。

**方案**：按 token 总量控制历史上下文。

```
固定 token 预算 (8000)
     ↓
从最新消息往前扫描 → 累计 token 数 ≤ 预算 → 取这批消息 → 超出预算的丢弃
```

**Token 估算算法**（`utils/tokens.ts`）：

- CJK 字符：~1.5 字符/token
- 英文/数字/其他：~4 字符/token
- 精度约 ±15%，对滑动窗口控制足够

**配置**：`.env` 中 `HISTORY_MAX_TOKENS=8000`，可按 LLM 上下文大小灵活调整。

---

### 5.3 压缩重试 + 失败标记

**问题**：`compressConversation` 单次 LLM 调用，失败静默丢弃。

**方案**：最多 2 次重试（指数退避 1s → 2s），全部失败后标记 `summaryError=true`。

```
┌─ compressConversation ───────────────┐
│  1. LLM 调用                         │
│     ├─ 成功 → 写入 summary + recap + │
│     │   summaryError=false +         │
│     │   summaryAt=now()              │
│     └─ 失败 → 等待 1s                │
│  2. LLM 调用                         │
│     ├─ 成功 → 同上                   │
│     └─ 失败 → 等待 2s                │
│  3. LLM 调用                         │
│     ├─ 成功 → 同上                   │
│     └─ 失败 → markSummaryFailed()    │
│              summaryError=true       │
└──────────────────────────────────────┘
```

**降级策略**：如果 `recap` 解析失败但 `summary` 存在，仍保存 `summary`（不因一个字段丢失放弃全部）。

---

### 5.4 分层摘要

**问题**：单一摘要混在一起，"用户订了 3000 预算"和"用户对川菜很感兴趣"混为一谈。

**方案**：一次 LLM 调用输出两层摘要——`summary`（关键决策）和 `recap`（对话脉络）。

**LLM 输出格式**：

```
### 关键决策
目的地成都，4天，预算3500，偏好文化+美食，决定住春熙路

### 对话脉络
讨论过武侯祠→宽窄巷子路线，用户对火锅兴趣浓厚，问了两次住宿推荐
```

**系统提示注入**：

```
# 对话历史摘要（关键决策）
目的地成都，预算3500...
请结合以上决策信息回答用户。

# 对话脉络
讨论过武侯祠→宽窄巷子路线...
了解以上讨论脉络，有助于理解用户的完整意图。
```

**降级**：如果 LLM 输出不符合格式（缺了脉络段），至少保存决策摘要。

---

## 六、数据库变更

```prisma
model Conversation {
  summary      String?   @db.Text     // 关键决策摘要（已有，行为从覆盖改为追加）
  recap        String?   @db.Text     // 对话脉络摘要（新增）
  summaryError Boolean?  @default(false)  // 压缩失败标记（新增）
  summaryAt    DateTime?              // 上次压缩成功时间（新增）
}
```

---

## 七、提交记录

| Commit | 内容 |
|---|---|
| `400ac62` | Priority 1: 增量摘要（追加模式） |
| `b9424a5` | Priority 2: 自适应 Token 窗口 |
| `81cac39` | Priority 3: 压缩重试 + 失败标记 |
| `fb93ff2` | Priority 4: 分层摘要 |
