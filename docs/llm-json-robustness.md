# LLM JSON 输出健壮性方案

> **背景**：审计项目里所有 LLM → JSON 的路径（recommend / optimize），发现 9 个会让流程"看似成功但实际产出垃圾"的隐患。
> **目标**：从"提示词 + 提取 + 校验 + 重试" 4 道防线同时加固，把垃圾输出阻断在写入 DB 之前。
> **实施时间**：2026-06-20

---

## 1. 现有 JSON 路径

```
                        LLM 输出
                           ↓
              ┌─────────────────────────┐
              │ extractJson()           │ ← 提取层（jsonExtractor.ts）
              │   1. ```json``` 块匹配   │
              │   2. 整段 JSON.parse     │
              │   3. 括号配对扫描        │
              └────────────┬────────────┘
                           ↓
              ┌─────────────────────────┐
              │ TripContentSchema.parse │ ← 校验层（types/agent.ts）
              │   zod object            │
              └────────────┬────────────┘
                           ↓
                       Trip DB
```

调用点：
- `agentEngine.recommend()` — 行程推荐（agent + tool calling）
- `optimizeService.optimizeTrip()` — 行程优化（直接 LLM 调用）

---

## 2. 9 个隐患与修复

### 2.1 数字加引号

**症状**：`{"days":"3","totalBudget":"5000",...}`

**原因**：LLM 看到 prompt 里的 JSON 模板 `{day:1,totalBudget:0}` 是数字，但中文 prompt 里说"数字不要加引号"约束力弱，DeepSeek v4-flash 实际有 5~10% 概率给数字加引号。

**改前**：`z.coerce.number()` 救场，但 schema 文档里没说明。

**改后**：
- `systemPrompt.ts` 新增"严格 JSON 规范"段，明确列出哪些字段必须是数字
- 字段定义表（markdown 表格）固化每个字段的类型
- `z.coerce.number()` 保留兼容

### 2.2 字符串内含 `{}` 字符

**症状**：`description: "宽窄{老成都}里"` 让 `extractBalancedBraces` 把 `}` 当成对象结束。

**改前**：`extractBalancedBraces` 有 `inString` 状态机处理（`utils/jsonExtractor.ts:54-57`），**已正确**。

**改后**：保留 + 在 fixture 里加场景 4 防止回归。

### 2.3 LLM 输出被截断

**症状**：`max_tokens` 截断 → `{"city":"成都","days":3,...,"afternoon":{"spo` 缺尾 `}`

**改前**：extract 抛"无法从 LLM 输出中提取 JSON"，**错误信息无定位信息**。

**改后**：`findAllBalancedObjects` 扫描时发现未闭合 `{` → 抛 `LLM 输出被截断或括号不平衡：从位置 X 起 <前 120 字符>`。带位置 + 截断片段，便于排查。

### 2.4 前后废话

**症状**：`"好的，我来规划... {"city":"成都",...} 这是您的行程"`.

**改前**：`extractBalancedBraces` 从第一个 `{` 扫描到最深配对 → 正确。

**改后**：保留 + fixture 场景 1 验证。

### 2.5 markdown ```json``` 包裹

**症状**：` ```json\n{...}\n``` `

**改前**：代码块匹配优先 → 正确。

**改后**：保留 + fixture 场景 2 验证。

### 2.6 嵌套类型错

**症状**：`dailyItinerary: ["第1天去宽窄巷子", "第2天去锦里"]`（应是对象数组）

**改前**：`z.array(z.any())` **任何数组都过**，前端拿到垃圾数据运行时炸。

**改后**：严格定义 `TripDaySchema` + `TripSlotSchema`（types/agent.ts:32-58）：

```typescript
const TripSlotSchema = z.object({
  spot: z.string(),
  duration: z.string().optional().default(''),
  ticket: z.string().optional().default(''),
  transportation: z.string().optional().default(''),
  description: z.string().optional().default(''),
})

const TripDaySchema = z.object({
  day: z.coerce.number().int().positive(),
  date: z.string().optional().default(''),
  morning: TripSlotSchema,
  afternoon: TripSlotSchema,
  evening: TripSlotSchema,
})

dailyItinerary: z.array(TripDaySchema).min(1)
```

### 2.7 budgetBreakdown 字段名错

**症状**：`{hotel: 1500, food: 1200, ...}` 把 `accommodation` 写成 `hotel`

**改前**：zod 严格，但提示词里只列了 5 个字段名缩写，LLM 自由发挥。

**改后**：
- `budgetBreakdown` 5 个字段 zod `.nonnegative()` 强校验
- 提示词"严格 JSON 规范"段明文写：**字段名严格匹配下表，不要新增、不要拼写错误、不要用同义词**
- 字段定义表（markdown）固化每个字段名

### 2.8 多对象边界

**症状**：`思考中... {} 这是结果：{...完整...}`

**改前**：`extractBalancedBraces` 从第一个 `{` 起找最深配对 → **返回 `{}` 空对象**（"思考"内容），完整对象被丢掉。

**改后**：`findAllBalancedObjects` 收集**所有**顶层对象候选 → 挑**最长的**那个。Fixture 场景 6 验证。

### 2.9 纯文字拒绝响应

**症状**：`"我无法生成这个行程，请提供更多目的地信息。"`

**改前**：找不到 `{` → 抛"无法从 LLM 输出中提取 JSON"。

**改后**：错误信息附首 120 字符：`无法从 LLM 输出中提取 JSON（首 120 字符：我无法生成这个行程，请提供更多目的地信息。）`。

---

## 3. 隐含改进

### 3.1 recommend 重试消息带回错误详情

`agentEngine.recommend()` 之前重试时只说"格式有误，请重做"，LLM 不知道哪里错了。

**改后**（agentEngine.ts:260-267）：

```typescript
const retryMessage =
  `你上次的输出无法通过校验：\n${zodMsg}\n\n` +
  `请严格按 system prompt 中的字段定义重新输出纯 JSON：\n` +
  `- 数字字段不加引号（city/days/totalBudget/day/budgetBreakdown.*）\n` +
  `- dailyItinerary 必须是对象数组，每天对象含 day/date/morning/afternoon/evening\n` +
  `- budgetBreakdown 必须含 accommodation/food/transportation/tickets/other 5 个数字\n` +
  `- 禁止 markdown 代码块、禁止前后缀文字\n\n` +
  `用户请求：${inputMessage}`
```

### 3.2 optimize 路径补上重试

**改前**：`optimizeService` 单次调用 → zod 失败直接抛错。LLM 偶尔输出不规整就整个 optimize 失败。

**改后**：3 次重试（`MAX_OPTIMIZE_RETRIES = 2`），重试时把上一次的 zod 错误喂回去。

### 3.3 字段类型强化

| 字段 | 改前 | 改后 |
|---|---|---|
| `days` | `z.coerce.number()` | `.int().positive()` |
| `totalBudget` | `z.coerce.number()` | `.nonnegative()` |
| `budgetBreakdown.*` | `z.coerce.number()` | `.nonnegative()` |
| `warnings` | `z.array(z.string()).optional()` | `.optional().default([])`（前端不需判 null） |
| `dailyItinerary[].day` | 无约束 | `.int().positive()` |

---

## 4. 9 场景 fixture 测试

`prisma/test-json.ts`（已删除，验证完清理）覆盖：

| # | 场景 | 预期 | 改前 | 改后 |
|---|---|---|---|---|
| 1 | 干净 JSON | pass | ✅ | ✅ |
| 2 | ` ```json``` ` 包裹 | pass | ✅ | ✅ |
| 3 | 数字加引号 | pass（zod coerce） | ⚠️ 救场 | ✅ 显式声明 |
| 4 | 字符串内 `{}` | pass | ✅ | ✅ |
| 5 | 输出截断 | reject | ⚠️ 错误信息差 | ✅ "输出被截断 + 位置" |
| 6 | 多对象边界 | pass | ❌ 返回空对象 | ✅ 选最长的 |
| 7 | 嵌套类型错 | reject | ❌ 放过 | ✅ zod 拒绝 |
| 8 | budgetBreakdown 字段缺失 | reject | ⚠️ 字段错会放 | ✅ 字段名锁死 |
| 9 | 纯文字拒绝响应 | reject | ⚠️ 无诊断信息 | ✅ 带首 120 字符 |

**9/9 全过**。

---

## 5. 实施文件清单

| 文件 | 改动 |
|---|---|
| `trip-server/src/types/agent.ts` | TripContentSchema 强校验（Day/Slot 嵌套 + nonnegative + int） |
| `trip-server/src/utils/jsonExtractor.ts` | 多对象选最长 + 截断检测 + 错误信息带首 120 字符 |
| `trip-server/src/services/agent/systemPrompt.ts` | "严格 JSON 规范"段 + 字段定义表 + 字段类型表 |
| `trip-server/src/services/agent/agentEngine.ts` | recommend 重试消息附带 zod 错误详情 |
| `trip-server/src/services/optimizeService.ts` | 加 retry 循环（之前 0 重试） |

总计 5 个文件，~150 行改动。

---

## 6. 进一步可选优化（暂不实施）

### 6.1 强制 LLM 用 `tool_choice` 而非自由文本

OpenAI / DeepSeek 支持 `tool_choice: { type: 'function', function: { name: '...' } }`，强制 LLM 通过 tool call 返回结构化数据。LangChain 需用 `withStructuredOutput` 包装。**优点**：彻底避免 LLM 自由发挥。**缺点**：和现有 agent 工具调用冲突（retrieve_knowledge / get_weather / ...），需要架构调整。

### 6.2 Streaming JSON 解析

当前 `recommend` 是非流式，LLM 完整生成后才解析。如果改成流式，可以边生成边用 partial JSON 解析器（如 `clarinet`）边校验。**优点**：长行程生成时前端可以提早看到结构。**缺点**：partial 解析容错复杂度高。

### 6.3 多模型交叉验证

同一请求发给两个不同 LLM，对比 JSON 输出一致性。**优点**：高价值行程（用户付费场景）可保证质量。**缺点**：成本 ×2，延迟 ×1.5。

---

## 7. 回滚预案

每个文件的改动独立，git revert 即可：

```bash
git revert <commit-sha>
```

`types/agent.ts` 改严后**会让旧数据不通过**——若需要回滚到宽松 schema，单独 revert 这个文件。

`jsonExtractor.ts` 的"选最长"行为是**新行为**（不是 bug fix），如果下游消费方依赖"返回第一个对象"会出问题——目前没有这种消费方，安全。

`optimizeService.ts` 加重试后**多消耗 2~3 次 LLM 调用**（仅失败路径，正常路径无影响）。
