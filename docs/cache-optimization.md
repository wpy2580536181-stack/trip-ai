# DeepSeek 缓存命中率优化方案

> **背景**：账单显示 deepseek-v4-flash 平均命中率 54.96%（去掉 06-10 批量测试 1 天），而同账号 06-06 pro 模型命中率达 90.24%。差距主要来自前缀稳定性。
> **目标**：在 7 天内把命中率达到 80%+（命中价 0.00002 vs 未命中 0.001，差距 50x）。
> **实施时间**：2026-06-20 起

---

## 1. DeepSeek 缓存机制回顾

### 1.1 工作原理

DeepSeek 的"输入缓存"采用 **prefix matching**：

- 整段请求（system + messages + tools）做 hash 写入磁盘
- 下次请求如果**前 N 个 token 完全一致**，未变化部分按 `cache_hit` 价格计费
- 价格（v4-flash）：hit = 0.00002 元/千 token，miss = 0.001 元/千 token → **差 50x**

### 1.2 命中与失效的两个层级

| 层级 | 命中条件 | 失效条件 |
|---|---|---|
| **跨请求** | 同一会话 N 轮：system + 历史消息前缀一致 | system 改了 / 摘要变了 / 偏好变了 |
| **单次请求内部** | 一次 agent 调用 = N 轮 LLM | 每轮 LLM 都是独立请求，前缀从头算 |

### 1.3 为什么我们命中率低

按账单数据反推（2026-06 真实数据）：

| 日期 | 命中 | 未命中 | 命中率 | 推断原因 |
|---|---|---|---|---|
| 06-03 | 0 | 641 | 0.00% | 短消息，系统 prompt + 用户输入几乎不重复 |
| 06-08 | 2,176 | 38,531 | 5.35% | 首次跑批量，cache 还没积累 |
| 06-10 | 2,817,792 | 45,503 | 98.41% | 同 session 重复工具调用，cache 全接住（异常值） |
| 06-12 | 274,560 | 146,221 | 65.25% | 多用户多对话活跃日 |
| 06-14 | 23,808 | 45,995 | 34.11% | 摘要更新频繁 → system prompt 整体变化 |
| 06-15 | 115,072 | 91,001 | 55.84% | 摘要更新 + 多轮 agent 工具调用 |

---

## 2. 破前缀点定位（基于代码）

通过 `systemPrompt.ts`、`agentEngine.ts`、`summaryService.ts` 的完整阅读，定位 **5 个核心破前缀点**：

### 🔴 2.1 摘要/脉络重写（最致命）

`summaryService.ts:67-72` 当前实现：

```typescript
// 增量模式：把旧摘要 + 新消息一起给 LLM，让 LLM "重写" 摘要
systemMsg = '请分析新对话和已有摘要，输出更新后的两层摘要'
prompt = `已有摘要：\n${previousSummary}\n\n新对话：\n${dialogText}\n\n请输出两层摘要...`
```

**问题**：LLM 每次输出内容**字面不同**（即使语义等价），system prompt 里的 `### 关键决策` 段就变了。

**影响**：`systemPrompt.ts:50,58` 注入到 prompt 的 `conversationSummary` 变了 → **整个 system prompt 的 hash 全变** → 后续所有请求全部 cache miss。

### 🔴 2.2 偏好字段顺序不稳定

`systemPrompt.ts:43`：

```typescript
parts.push(`# 用户偏好\n${JSON.stringify(userPreferences, null, 2)}...`)
```

`JSON.stringify` 按对象插入顺序输出。前端 `UserPreferences` 在 `user.ts:14-20` 是固定 5 个 key（`travelStyle` / `budgetLevel` / `pace` / `avoidCrowds` / `interests`），但：

- 老用户中途编辑过 → key 顺序可能不一致
- 新用户 `preferences = {}` → `Object.keys().length === 0` → **整段消失** → 前缀变化

**影响**：同一用户每次请求的 system prompt 都可能不同。

### 🔴 2.3 偏好空值时整段消失

`systemPrompt.ts:39`：

```typescript
if (userPreferences && Object.keys(userPreferences).length > 0) {
  parts.push(`# 用户偏好 ...`)  // 空偏好时整段不输出
}
```

**影响**：用户从"有偏好"改为"清空偏好" → system prompt 长度直接变短 → 前缀 hash 必变。

### 🟡 2.4 Agent 多轮 LLM 内部前缀翻倍

`agentEngine.ts:108` 使用 `streamEvents` + `ToolCallingAgent`，一次完整 agent 决策可能触发 N 轮 LLM：

```
请求 1: [sys, user]              → cache miss
请求 2: [sys, user, ai₁, tool₁]  → cache miss（与 1 前缀不同）
请求 3: [sys, user, ai₁, tool₁, ai₂, tool₂]  → cache miss
```

**影响**：哪怕第一步命中了 prefix，agent 内部循环的每一步前缀都重新 hash。

### 🟡 2.5 同一对话内"用户消息"在固定位置

`agentEngine.ts:60-62` 的 prompt 模板：

```typescript
['system', escaped],
['placeholder', '{chat_history}'],
['human', '{input}'],
['placeholder', '{agent_scratchpad}'],
```

**问题**：当前**新用户消息没作为独立 human message 注入**到 `chat_history`，而是直接通过 `{input}` 占位符传入。LangChain 会把它**拼到 chat_history 之后**——当 chat_history 是空时，`{input}` 紧跟在 system 后；当 chat_history 有内容时，`{input}` 跟在历史后 → **位置不固定**，cache miss。

---

## 3. 优化方案（按 ROI 排序）

### 🥇 P0-1：system prompt 字段固定化（0 成本，预计 +20~30%）

#### 改动点

**`systemPrompt.ts`**：把 5 段都改成"始终输出 + 占位符兜底"：

```typescript
// 改前
if (userPreferences && Object.keys(userPreferences).length > 0) {
  parts.push(`\n# 用户偏好\n${JSON.stringify(userPreferences, null, 2)}...`)
}

// 改后
const PREF_KEYS = ['travelStyle', 'budgetLevel', 'pace', 'avoidCrowds', 'interests'] as const
const fixedPrefs = PREF_KEYS.reduce<Record<string, any>>((acc, k) => {
  acc[k] = userPreferences?.[k] ?? null
  return acc
}, {})
parts.push(`\n# 用户偏好（固定字段，未设置时为 null）\n${JSON.stringify(fixedPrefs, null, 2)}`)
```

同样对 `conversationSummary` / `conversationRecap` 改成始终占位：

```typescript
parts.push(`\n# 对话历史摘要\n${conversationSummary ?? '（暂无）'}`)
parts.push(`\n# 对话脉络\n${conversationRecap ?? '（暂无）'}`)
```

**收益**：
- 同一用户的 system prompt 长度恒定
- 字段顺序锁定 → JSON 序列化结果稳定
- 偏好为空/不为空切换 → 不再影响前缀

### 🥇 P0-2：固定 prompt 模板位置（0 成本，预计 +5~10%）

#### 改动点

**`agentEngine.ts:58-63`**：把"用户当前消息"作为独立 human message 注入，而不是依赖 `{input}` 占位：

```typescript
// 改前
const prompt = ChatPromptTemplate.fromMessages([
  ['system', escaped],
  ['placeholder', '{chat_history}'],
  ['human', '{input}'],
  ['placeholder', '{agent_scratchpad}'],
])
const input = { input: message, chat_history: historyMessages }

// 改后：固定结构，user 消息作为 chat_history 追加的最后一条
const prompt = ChatPromptTemplate.fromMessages([
  ['system', escaped],
  ['placeholder', '{chat_history}'],
  ['placeholder', '{agent_scratchpad}'],
])
const input = { chat_history: [...historyMessages, new HumanMessage(message)] }
```

**收益**：用户消息始终在 chat_history 末尾，位置固定。

### 🥈 P1-1：摘要 append 模式（接受质量换命中率）

#### 改动点

**`summaryService.ts`**：把"重写"改成"追加"——不再给 LLM 旧摘要，只让 LLM 对**新增的旧消息**生成一段新摘要，**追加到 conversation.summary 后面**（用 `### [追加于 {date}] ` 作为分节符）。

```typescript
// 改前
prompt = `已有摘要：\n${previousSummary}\n\n新对话：\n${dialogText}\n\n请输出更新后的两层摘要...`

// 改后
prompt = `请对以下对话生成一段新摘要（不超过 200 字）。
摘要将追加到对话历史摘要的末尾，所以请只关注本次新对话中出现的新决策/新方向，不要重复已有内容。\n\n新对话：\n${dialogText}`

// commitSummary 改成追加
async function commitSummary(conversationId, newChunk, recap) {
  const conv = await prisma.conversation.findUnique({ where: { id: conversationId }, select: { summary: true } })
  const merged = conv?.summary
    ? `${conv.summary}\n\n### 追加于 ${new Date().toISOString().slice(0, 10)}\n${newChunk}`
    : newChunk
  await prisma.conversation.update({
    where: { id: conversationId },
    data: { summary: merged, recap, summaryError: false, summaryAt: new Date() },
  })
}
```

**收益**：
- 摘要只在尾部追加 → 旧摘要部分字面不变
- 命中段 = system prompt 前 800 token（系统说明 + 工具描述）→ 几乎永远命中
- 代价：摘要会越来越长，超过预算时由 token 窗口自然丢弃

### 🥈 P1-2：单次 agent 决策降级（保留为可选）

> 暂不实施，等 P0/P1 效果出来后再评估

agent 工具调用合并方案：见 §5 未来选项

### 🥉 P2：跨用户共享前缀（架构改造）

把所有用户共享的"工具描述 + 角色说明"提取为固定的 `staticSystemPrompt`，放在请求最前；用户级（preferences）、会话级（summary）放后面。**但 LangChain `ChatPromptTemplate` 是单 system 字段**，需要：

1. 改用 `messages` 数组直接构造（不经过模板）
2. 或拆成两个 system 段（LangChain 会合并，但 cache 按段独立 hash）

**收益**：跨用户也能命中"工具描述"段（约 500 token）。

---

## 4. 实施计划

### 第 1 阶段：P0 改造（预计 2 天）

| 任务 | 文件 | 预计收益 |
|---|---|---|
| 1.1 偏好固定 5 字段 + 占位 null | `systemPrompt.ts` | +15% |
| 1.2 摘要/脉络始终占位 | `systemPrompt.ts` | +5% |
| 1.3 user 消息移入 chat_history | `agentEngine.ts:58-63` | +10% |
| 1.4 端到端测试 | 手动 | - |

**关键验证**：
- 同一用户连续发 5 轮 → 5 个请求中 4+ 个 hit（v4-flash 后端日志可看 `prompt_cache_hit_tokens`）
- 偏好空/非空切换 → 不破前缀

### 第 2 阶段：P1-1 摘要 append（预计 1 天）

| 任务 | 文件 | 预计收益 |
|---|---|---|
| 2.1 摘要 prompt 改为"只生成新段" | `summaryService.ts:66-72` | +10% |
| 2.2 commitSummary 改为追加 | `summaryService.ts:13-19` | - |
| 2.3 测试摘要增长 → 触发 token 窗口丢弃 | 手动 | - |

### 第 3 阶段：P2 跨用户共享（暂缓）

等 P0+P1 跑一周看真实命中率再决定。

### 第 4 阶段：验证（持续）

每天从 DeepSeek 后台导出账单 CSV，计算 `hit / (hit + miss)`：

- 目标：单日命中率 ≥ 80%
- 失败兜底：回滚 P1-1（保留 P0 改动）

---

## 5. 未来选项（暂不实施）

### 5.1 agent 工具调用合并

把 `ToolCallingAgent` 改成 `maxIterations: 1` + `earlyStoppingMethod: 'force'`，强制单次决策。**代价**：复杂多工具场景失效。**收益**：避免一次 agent 内部 2~3 轮 LLM 调用导致的前缀失效。

### 5.2 客户端预取工具结果

天气/距离/酒店这种"低风险"工具 → 前端在用户发送前预调用，结果拼到 system prompt 的"上下文快照"段，Agent 收到的是一次性完整上下文，不需要调工具。

### 5.3 Cache TTL 监测

加 endpoint `/api/admin/cache-stats` 调 DeepSeek `/v1/billing/usage` 拿命中率历史，绘图到 Admin 控制台。

---

## 6. 成本估算

按当前账单数据（5/6 v4-flash 共 3,678,324 tokens 输入）反推单月：

- 总输入 ≈ 3,678,324 × 3（10 天 → 1 月）= **~11M tokens/月**
- 当前命中率 55%：6.05M hit + 4.95M miss
  - 成本 = 6.05M × 0.00002/1000 + 4.95M × 0.001/1000 = 0.121 + 4.95 = **¥5.07/月**
- 目标命中率 80%（同样 11M 总输入）：8.8M hit + 2.2M miss
  - 成本 = 8.8M × 0.00002/1000 + 2.2M × 0.001/1000 = 0.176 + 2.20 = **¥2.38/月**
- **节省约 ¥2.69/月（53%）**

加上 v4-pro 偶用（命中率已 90%，基本无需优化），**单月节省约 ¥2.7**。规模小但实现成本接近 0，**纯纯的白送**。

---

## 7. 回滚预案

每个阶段独立 commit，回滚命令：

```bash
# 回滚 P1
git revert <P1-commit-sha>

# 回滚 P0
git revert <P0-commit-sha>
```

P0 改动只改 system prompt 拼装逻辑，不影响功能，**几乎无回滚必要**。
P1 摘要 append 是单向操作（旧摘要保留在 DB），如要回滚到重写模式需手动改 `commitSummary` + 历史摘要截断。
